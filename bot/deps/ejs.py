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
    DependenciesUpdateResultType,
    Project,
    denormalized_tags,
    make_commit_body,
    make_commit_line,
    package_diff_dict,
)
from bot.git import Commit
from bot.github import (
    GITHUB_URL_RE,
    GitHubAPICaller,
)
from bot.knowledge import (
    BOT_BEGIN_HTML_TAG,
    BOT_END_HTML_TAG,
    NPM_PACKAGES,
)
from bot.utils import (
    BaseAPICaller,
    BotError,
)

try:
    import yaml
except ImportError:
    yaml = None


def get_package_lock_packages(package_lock: dict[str, typing.Any]) -> dict[str, str]:
    return {
        # Remove prefix, e.g.: node_modules/@typescript-eslint/utils -> @typescript-eslint/utils
        package_name.removeprefix('node_modules/'): package_info['version']
        for package_name, package_info in package_lock['packages'].items()
        # Omit nested deps, e.g.: node_modules/@typescript-eslint/typescript-estree/node_modules/minimatch
        if package_name and '/node_modules/' not in package_name
    }


def make_ejs_commit_message(
    all_updates: DependenciesUpdateResultType,
    updates: DependenciesUpdateResultType,
    dev_updates: DependenciesUpdateResultType,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
    serialized_data: str | None = None,
) -> str:
    addendum = f'\n\n{addendum}\n' if addendum else '\n'
    serialized_data = f'\n---\n\n{serialized_data}\n' if serialized_data else ''

    if len(all_updates) > 1:
        if not updates or not dev_updates:
            commit_body = make_commit_body(all_updates)
        else:
            commit_body = '\n\n'.join((
                make_commit_body(updates),
                make_commit_body(dev_updates),
            ))

        return ''.join((
            make_ejs_commit_title(updates, dev_updates, prefix=prefix),
            '\n\n',
            commit_body,
            addendum,
            serialized_data,
        ))
    else:
        package, (old, new) = next(iter(all_updates.items()))

        return ''.join((
            make_commit_line(package, old, new, prefix=prefix or ''),
            addendum,
            serialized_data,
        ))


def make_ejs_commit_title(
    updates: DependenciesUpdateResultType,
    dev_updates: DependenciesUpdateResultType,
    *,
    prefix: str | None = None,
) -> str:
    deps_count = len(updates)
    deps_str = f'{deps_count} dependenc{"ies" if deps_count > 1 else "y"}'

    dev_deps_count = len(dev_updates)
    dev_deps_str = f'{dev_deps_count} development dependenc{"ies" if dev_deps_count > 1 else "y"}'

    return ''.join((
        prefix or '',
        'Update ',
        deps_str if deps_count else '',
        ' & ' if deps_count and dev_deps_count else '',
        dev_deps_str if dev_deps_count else '',
    ))


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
        self.pnpm_config_path = self.project_path / 'pnpm-workspace.yaml'
        self.node_modules_path = self.project_path / 'node_modules'

    def _find_exe(self, /, basename: str) -> str:
        location = shutil.which(basename)
        if not location:
            raise BotError(f'{basename} executable could not be found')
        if not os.access(location, os.F_OK | os.X_OK) or os.path.isdir(location):
            raise BotError(f'unable to execute {location!r}')

        return location

    def load_package_json(self, /) -> dict[str, typing.Any]:
        with self.package_json_path.open('rb') as f:
            return json.load(f)

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
    _COOLDOWN_DAYS = 7
    _COOLDOWN_MINS = _COOLDOWN_DAYS * 60 * 24  # pnpm
    _PNPM_COOLDOWN_KEY = 'minimumReleaseAge'

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
        self.pnpm_config_path = self.project.pnpm_config_path
        self.node_modules_path = self.project.node_modules_path
        self.load_package_json = self.project.load_package_json
        self.load_package_lock = self.project.load_package_lock

    def _verify_pnpm_cooldown(self, /) -> bool:
        if yaml is None:
            raise BotError('the pyyaml package (yaml library) is required')

        config = yaml.safe_load(self.pnpm_config_path.read_text())

        return config.get(self._PNPM_COOLDOWN_KEY) == self._COOLDOWN_MINS

    def update(
        self,
        /,
        *,
        upgrade_only: str | None = None,
        **kwargs,
    ) -> tuple[set[pathlib.Path], DependenciesUpdateResultType]:
        # Stash original lockfile for package diff-ing post-update
        og_lockfile = self.load_package_lock()

        updated_paths: set[pathlib.Path] = set()

        # Create (or verify there is) a pnpm config file with the appropriate cooldown policy
        if not self.pnpm_config_path.is_file():
            self.pnpm_config_path.write_text(f'{self._PNPM_COOLDOWN_KEY}: {self._COOLDOWN_MINS}\n')
        elif not self._verify_pnpm_cooldown():
            raise BotError(f'pnpm cooldown is not configured as {self._COOLDOWN_DAYS} days')

        # Upgrade package(s)
        if upgrade_only:
            old_version = self.load_package_json()['dependencies'][upgrade_only]
            self.pnpm('upgrade', '--latest', upgrade_only)
            new_version = self.load_package_json()['dependencies'][upgrade_only]
            if old_version == new_version:
                return updated_paths, {}
        else:
            self.pnpm('upgrade', '--latest', '--dev')
        updated_paths.add(self.package_json_path)

        if self.node_modules_path.is_dir():
            print('[bot] Removing node_modules', file=sys.stderr)
            shutil.rmtree(str(self.node_modules_path))

        if not upgrade_only and self.package_lock_path.is_file():
            print('[bot] Removing package-lock.json', file=sys.stderr)
            self.package_lock_path.unlink()

        # Generate base package-lock.json
        self.npm('config', 'set', f'min-release-age={self._COOLDOWN_DAYS}')
        self.npm('install')
        updated_paths.add(self.package_lock_path)

        # Generate new pnpm-lock.yaml from package-lock.json
        self.pnpm('import')
        updated_paths.add(self.pnpm_lock_path)

        # Generate new bun.lock from package-lock.json
        if self.bun_lock_path.is_file():
            print('[bot] Removing bun.lock', file=sys.stderr)
            self.bun_lock_path.unlink()
        self.bun('pm', 'migrate', '--force')
        # bun<1.2 writes a bun.lockb file instead of bun.lock
        if not self.bun_lock_path.is_file():
            raise BotError('bun.lock does not exist')
        updated_paths.add(self.bun_lock_path)

        # Generate deno.lock
        self.deno('install', f'--minimum-dependency-age=P{self._COOLDOWN_DAYS}D')
        updated_paths.add(self.deno_lock_path)

        all_updates = package_diff_dict(
            get_package_lock_packages(og_lockfile),
            get_package_lock_packages(self.load_package_lock()),
        )

        return updated_paths, all_updates

    def _generate_report(
        self,
        /,
        updates: DependenciesUpdateResultType,
        npm_api: NPMAPICaller,
        *,
        header: str | None = None,
    ) -> collections.abc.Iterator[str]:
        if not updates:
            return

        gh_tags_cache: dict[tuple[str, str], list[str]] = {}

        if header:
            yield f'## {header}\n'

        yield 'package | old | new | diff | homepage'
        yield '--------|-----|-----|------|---------'
        for package, (old, new) in sorted(updates.items()):
            metadata = npm_api.get_package_metadata(package)
            homepage_url = metadata.get('homepage') or ''

            if package in NPM_PACKAGES:
                github_info = NPM_PACKAGES[package]
            else:
                project_urls = [homepage_url]

                if bugs := metadata.get('bugs'):
                    if isinstance(bugs, dict) and (bugs_url := bugs.get('url')):
                        project_urls.append(bugs_url)
                    elif isinstance(bugs, str):
                        project_urls.append(bugs)

                if repository := metadata.get('repository'):
                    if isinstance(repository, dict) and (repo_url := repository.get('url')):
                        project_urls.append(repo_url)
                    elif isinstance(repository, str):
                        project_urls.append(repository)

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
                    md_old = md_old.lstrip('.')
                    md_new = '.'.join(new_parts[:offset]) + '.***' + '.'.join(new_parts[offset:]) + '***'
                    md_new = md_new.lstrip('.')

            compare = ''
            if github_info and old and new:
                cache = gh_tags_cache.setdefault((github_info['owner'], github_info['repo']), [])

                tag_prefixes = [github_info.get('tag_prefix') or 'v']
                # Match tag prefix for monorepo packages, e.g. `core-v1.0.0` for `@humanfs/core`
                if basename := package.partition('/')[2]:
                    tag_prefixes.append(f'{basename}-v')

                old_tag_matches = denormalized_tags(old, *tag_prefixes)
                new_tag_matches = denormalized_tags(new, *tag_prefixes)

                old_tag = next((tag for tag in cache if tag in old_tag_matches), None)
                new_tag = next((tag for tag in cache if tag in new_tag_matches), None)

                if not (old_tag and new_tag):
                    tags_list = self.gh.paginated_results(
                        self.gh.list_repository_tags,
                        github_info['owner'],
                        github_info['repo'],
                        searches=[{'name': old_tag_matches}, {'name': new_tag_matches}],
                    )

                    old_tag = next((tag['name'] for tag in tags_list if tag['name'] in old_tag_matches), None)
                    if old_tag:
                        cache.append(old_tag)

                    new_tag = next((tag['name'] for tag in tags_list if tag['name'] in new_tag_matches), None)
                    if new_tag:
                        cache.append(new_tag)

                github_url = 'https://github.com/{owner}/{repo}'.format(**github_info)
                if new_tag:
                    md_new = f'[{md_new}](<{github_url}/releases/tag/{new_tag}>)'
                if old_tag:
                    md_old = f'[{md_old}](<{github_url}/releases/tag/{old_tag}>)'
                if new_tag and old_tag:
                    compare = f'[`{old_tag}...{new_tag}`](<{github_url}/compare/{old_tag}...{new_tag}>)'

            yield ' | '.join((
                f'[**`{package}`**](<https://www.npmjs.com/package/{package}>)',
                md_old,
                md_new,
                compare,
                f'[link](<{homepage_url}>)' if homepage_url else '',
            ))

    def _make_pull_request_description(
        self,
        /,
        dependencies: DependenciesUpdateResultType,
        dev_dependencies: DependenciesUpdateResultType,
        merge_commit_message: str,
    ) -> str:
        npm_api = NPMAPICaller(verbose=self.gh.verbose)

        return '\n'.join((
            f'{BOT_BEGIN_HTML_TAG}\n',
            *self._generate_report(dependencies, npm_api, header='Dependencies'),
            '',
            *self._generate_report(dev_dependencies, npm_api, header=' Development dependencies'),
            '\n```',
            merge_commit_message,
            '```\n',
            f'{BOT_END_HTML_TAG}\n',
        ))

    def parse_results(
        self,
        /,
        all_updates: DependenciesUpdateResultType,
        existing_commits: list[Commit],
        *,
        commit_prefix: str | None = None,
        commit_addendum: str | None = None,
        **kwargs,
    ) -> tuple[str, str, str]:
        """Returns a tuple of pull request description, commit message, and merge commit message"""

        all_reconciled_updates = self.reconcile_updates(
            self.get_previous_updates(existing_commits),
            all_updates,
        )

        dependencies = self.load_package_json()['dependencies']
        updates: DependenciesUpdateResultType = {}
        dev_updates: DependenciesUpdateResultType = {}
        reconciled_updates: DependenciesUpdateResultType = {}
        reconciled_dev_updates: DependenciesUpdateResultType = {}

        for package_name, diff_tuple in all_updates.items():
            if package_name in dependencies:
                updates[package_name] = diff_tuple
            else:
                dev_updates[package_name] = diff_tuple

        for package_name, diff_tuple in all_reconciled_updates.items():
            if package_name in dependencies:
                reconciled_updates[package_name] = diff_tuple
            else:
                reconciled_dev_updates[package_name] = diff_tuple

        merge_commit_message = make_ejs_commit_message(
            all_reconciled_updates,
            reconciled_updates,
            reconciled_dev_updates,
            prefix=commit_prefix,
            addendum=commit_addendum,
        )

        return (
            self._make_pull_request_description(
                reconciled_updates,
                reconciled_dev_updates,
                merge_commit_message,
            ),
            make_ejs_commit_message(
                all_updates,
                updates,
                dev_updates,
                prefix=commit_prefix,
                addendum=commit_addendum,
                serialized_data=self.serialize_results(all_updates),
            ),
            merge_commit_message,
        )
