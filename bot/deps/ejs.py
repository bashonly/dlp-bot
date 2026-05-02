from __future__ import annotations

import collections.abc
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import typing

from bot.deps.common import (
    DependenciesUpdater,
    DependenciesUpdateResult,
    Project,
    denormalized_tags,
    make_commit_message,
    package_diff_dict,
)
from bot.github import (
    GITHUB_URL_RE,
    GitHubAPICaller,
)
from bot.knowledge import (
    BOT_BEGIN_HTML_TAG,
    BOT_END_HTML_TAG,
)
from bot.utils import (
    BaseAPICaller,
    BotError,
    VerificationError,
)


def get_package_lock_packages(package_lock: dict[str, typing.Any]) -> dict[str, str]:
    return {
        package_name.removeprefix('node_modules/'): package_info['version']
        for package_name, package_info in package_lock.items()
    }


class PNPMError(BotError):
    pass


class NPMError(BotError):
    pass


class BunError(BotError):
    pass


class DenoError(BotError):
    pass


class NPMAPIError(BotError):
    pass


class NPMAPICaller(BaseAPICaller):
    _API_BASE_URL = 'https://registry.npmjs.org/'
    _NOTE_PREFIX = 'npmjs'

    def __init__(self, /, *, verbose: bool = False):
        super().__init__(
            base_url=self._API_BASE_URL,
            verbose=verbose,
            note_prefix=self._NOTE_PREFIX,
            custom_exception=NPMAPIError,
        )

    def get_package_metadata(self, /, package: str):
        return self._fetch_json(f'/{package}', headers=self.headers)


class EJSProject(Project):
    def __init__(
        self,
        /,
        project_path: pathlib.Path,
        *,
        verbose: bool = False,
        **kwargs,
    ):
        super().__init__(project_path=project_path, **kwargs)
        self.verbose = verbose
        self._pnpm_exe = self._find_exe('pnpm')
        self._npm_exe = self._find_exe('npm')
        self._bun_exe = self._find_exe('bun')
        self._deno_exe = self._find_exe('deno')
        self.package_json_path = self.project_path / 'package.json'
        self.package_lock_path = self.project_path / 'package-lock.json'
        self.bun_lock_path = self.project_path / 'bun.lock'
        self.deno_lock_path = self.project_path / 'deno.lock'
        self.pnpm_lock_path = self.project_path / 'pnpm-lock.yaml'
        self.node_modules_path = self.project_path / 'node_modules'

    def _find_exe(self, /, basename: str) -> str:
        location = shutil.which(basename)
        if not location:
            raise BotError(f'{basename} executable could not be found')
        if not os.access(location, os.F_OK | os.X_OK) or os.path.isdir(location):
            raise BotError(f'unable to execute {location!r}')

        return location

    def load_package_lock(self, /) -> dict[str, typing.Any]:
        if not self.package_lock_path.is_file():
            return {}

        with self.package_lock_path.open('rb') as f:
            return json.load(f)

    def _run_exe(
        self,
        /,
        exe: str,
        *args: str,
        exc: type[Exception] = BotError,
        note: str = 'exe',
    ) -> list[str]:
        cmd = [exe, *args]

        if self.verbose:
            print(f'[{note}] {shlex.join(cmd)}', file=sys.stderr)

        try:
            output = subprocess.run(
                cmd,
                cwd=str(self.project_path),
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise exc(error)

        return output.splitlines()

    def pnpm(self, *args: str) -> list[str]:
        return self._run_exe(self._pnpm_exe, *args, exc=PNPMError, note='pnpm')

    def npm(self, *args: str) -> list[str]:
        return self._run_exe(self._npm_exe, *args, exc=NPMError, note='npm')

    def bun(self, *args: str) -> list[str]:
        return self._run_exe(self._bun_exe, *args, exc=BunError, note='bun')

    def deno(self, *args: str) -> list[str]:
        return self._run_exe(self._deno_exe, *args, exc=DenoError, note='deno')


class EJSDependenciesUpdater(DependenciesUpdater):
    def __init__(
        self,
        /,
        project: EJSProject,
        *,
        gh: GitHubAPICaller,
        **kwargs,
    ):
        super().__init__(project, **kwargs)
        self.gh = gh
        self.project_path = self.project.project_path
        self.pnpm = self.project.pnpm
        self.npm = self.project.npm
        self.bun = self.project.bun
        self.deno = self.project.deno
        self.package_json_path = self.project.package_json_path
        self.package_lock_path = self.project.package_lock_path
        self.bun_lock_path = self.project.bun_lock_path
        self.deno_lock_path = self.project.deno_lock_path
        self.pnpm_lock_path = self.project.pnpm_lock_path
        self.node_modules_path = self.project.node_modules_path
        self.load_package_lock = self.project.load_package_lock

    def check(self, /):
        self.project._run_exe(sys.executable, './check.py', exc=VerificationError, note='check')

    def update(
        self,
        /,
        **kwargs,
    ) -> tuple[set[pathlib.Path], DependenciesUpdateResult]:
        # Stash original lockfile for package diff-ing post-update
        og_lockfile = self.load_package_lock()

        updated_paths: set[pathlib.Path] = set()

        # Upgrade packages
        self.pnpm('upgrade', '--latest')
        updated_paths.add(self.package_json_path)

        if self.node_modules_path.is_dir():
            print('[bot] Removing node_modules', file=sys.stderr)
            shutil.rmtree(str(self.node_modules_path))

        if self.package_lock_path.is_file():
            print('[bot] Removing package-lock.json', file=sys.stderr)
            self.package_lock_path.unlink()

        # Generate base `package-lock.json`
        self.npm('install')
        updated_paths.add(self.package_lock_path)

        # Migrate to other package managers
        self.pnpm('import')
        updated_paths.add(self.pnpm_lock_path)
        self.bun('pm', 'migrate', '--force')
        updated_paths.add(self.bun_lock_path)

        # Make sure to use a deno with lockfile v4 (<2.3)
        self.deno('install', '--lockfile-only')
        updated_paths.add(self.deno_lock_path)

        # Ensure that `deno.json` is the same as `package-lock.json`.
        # Note: you may need to manually update the `ADDITIONAL_PACKAGES_NODE`
        # and/or `ADDITIONAL_PACKAGES_DENO` variables in `./check.py`.
        self.check()

        all_updates = package_diff_dict(
            get_package_lock_packages(og_lockfile),
            get_package_lock_packages(self.load_package_lock()),
        )

        return updated_paths, all_updates

    def _generate_report(
        self,
        /,
        all_updates: DependenciesUpdateResult,
    ) -> collections.abc.Iterator[str]:
        npm_api = NPMAPICaller(verbose=self.gh.verbose)

        yield 'package | old | new | diff'
        yield '--------|-----|-----|-----'
        for package, (old, new) in sorted(all_updates.items()):
            metadata = npm_api.get_package_metadata(package)
            homepage_url = metadata.get('homepage') or f'https://www.npmjs.com/package/{package}'

            project_urls = [homepage_url]
            if (bugs := metadata.get('bugs')) and (bugs_url := bugs.get('url')):
                project_urls.append(bugs_url)
            if (repository := metadata.get('repository')) and (repo_url := repository.get('url')):
                project_urls.append(repo_url)

            github_info = next(
                (mobj.groupdict() for url in project_urls if (mobj := GITHUB_URL_RE.search(url))),
                {},
            )

            md_old = old = old or ''
            md_new = new = new or ''
            if old and new:
                # bolden and italicize the differing parts
                old_parts = old.split('.')
                new_parts = new.split('.')

                offset = None
                for index, (old_part, new_part) in enumerate(zip(old_parts, new_parts, strict=False)):
                    if old_part != new_part:
                        offset = index
                        break

                if offset is not None:
                    md_old = '.'.join(old_parts[:offset]) + '.***' + '.'.join(old_parts[offset:]) + '***'
                    md_new = '.'.join(new_parts[:offset]) + '.***' + '.'.join(new_parts[offset:]) + '***'

            compare = ''
            if github_info:
                old_tag_matches = denormalized_tags(old)
                new_tag_matches = denormalized_tags(new)

                tags_list = self.gh.paginated_results(
                    self.gh.list_repository_tags,
                    github_info['owner'],
                    github_info['repo'],
                    searches=[{'name': old_tag_matches}, {'name': new_tag_matches}],
                )

                old_tag = next((tag['name'] for tag in tags_list if tag['name'] in old_tag_matches), None)
                new_tag = next((tag['name'] for tag in tags_list if tag['name'] in new_tag_matches), None)

                github_url = 'https://github.com/{owner}/{repo}'.format(**github_info)
                if new_tag:
                    md_new = f'[{md_new.lstrip(".")}](<{github_url}/releases/tag/{new_tag}>)'
                if old_tag:
                    md_old = f'[{md_old.lstrip(".")}](<{github_url}/releases/tag/{old_tag}>)'
                if new_tag and old_tag:
                    compare = f'[`{old_tag}...{new_tag}`](<{github_url}/compare/{old_tag}...{new_tag}>)'

            yield ' | '.join((
                f'[**`{package}`**](<{homepage_url}>)',
                md_old,
                md_new,
                compare,
            ))

    def _make_pull_request_description(
        self,
        /,
        all_updates: DependenciesUpdateResult,
    ) -> str:
        return '\n'.join((
            f'{BOT_BEGIN_HTML_TAG}\n',
            *self._generate_report(all_updates),
            f'\n{BOT_END_HTML_TAG}\n\n',
        ))

    def parse_results(
        self,
        /,
        all_updates: DependenciesUpdateResult,
        *,
        commit_prefix: str | None = None,
        commit_addendum: str | None = None,
        **kwargs,
    ) -> tuple[str, str]:
        """Returns a tuple of the pull request description and the merge commit message"""

        return (
            self._make_pull_request_description(all_updates),
            make_commit_message(all_updates, prefix=commit_prefix, addendum=commit_addendum),
        )
