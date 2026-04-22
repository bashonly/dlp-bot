from __future__ import annotations

import collections.abc
import contextlib
import dataclasses
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
import typing
import urllib.error

from bot.deps.common import (
    DependenciesUpdater,
    Project,
)
from bot.github import (
    GITHUB_URL_RE,
    GitHubAPICaller,
)
from bot.knowledge import (
    BOT_BEGIN_HTML_TAG,
    BOT_END_HTML_TAG,
    PYTHON_PACKAGES,
)
from bot.utils import (
    BotError,
    request,
)

EXTRAS_TABLE = 'project.optional-dependencies'

GROUPS_TABLE = 'dependency-groups'


class PyPIError(BotError):
    pass


class PythonProjectError(BotError):
    pass


class UVError(BotError):
    pass


type PythonUpdateResult = dict[str, tuple[str, str] | tuple[str, None] | tuple[None, str]]


def make_commit_message(
    all_updates: PythonUpdateResult,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
) -> str:
    if len(all_updates) > 1:
        return '\n\n'.join((
            make_commit_title(all_updates, prefix=prefix),
            make_commit_body(all_updates),
            f'{addendum or ""}\n',
        ))
    else:
        package, (old, new) = next(iter(all_updates.items()))

        return '\n\n'.join((
            make_commit_line(package, old, new, prefix=prefix or ''),
            f'{addendum or ""}\n',
        ))


def make_commit_title(all_updates: PythonUpdateResult, *, prefix: str | None = None) -> str:
    count = len(all_updates)
    return f'{prefix or ""}Update {count} dependenc{"ies" if count > 1 else "y"}'


def make_commit_body(all_updates: PythonUpdateResult) -> str:
    return '\n'.join(sorted(make_commit_line(package, old, new) for package, (old, new) in all_updates.items()))


def make_commit_line(package: str, old: str | None, new: str | None, *, prefix: str = '* ') -> str:
    if old is None:
        return f'{prefix}Add {package} {new}'

    if new is None:
        return f'{prefix}Remove {package} {old}'

    return f'{prefix}Bump {package} {old} => {new}'


def call_pypi_api(project: str, *, retries: int = 3):
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'dlp-bot',
    }
    for attempt in range(retries):
        print(f'Fetching package info from PyPI API: {project}', file=sys.stderr)
        try:
            with request(f'https://pypi.org/pypi/{project}/json', headers=headers, timeout=5) as resp:
                return json.load(resp)
        except (json.JSONDecodeError, urllib.error.HTTPError) as error:
            raise PyPIError(f'[{type(error).__name__}] {error}')
        except TimeoutError as error:
            if attempt < retries:
                print(
                    f'[bot] operation timed out, retrying ({attempt + 1} of {retries})',
                    file=sys.stderr,
                )
                continue
            raise PyPIError(f'[{type(error).__name__}] {error}')


def denormalized_tags(tag: str) -> list[str]:
    tags = [tag]
    # De-normalize calver tags like 2024.1.1 back to 2024.01.01
    if re.match(r'2[0-9]{3}\.[1-9]\.', tag) or re.match(r'2[0-9]{3}\.[0-9]{2}\.[1-9][^0-9]*', tag):
        with contextlib.suppress(ValueError):
            year, month, day = map(int, tag.split('.'))
            tags.append(f'{year}.{month:02d}.{day:02d}')

    return tags + [f'v{t}' for t in tags]


@dataclasses.dataclass(frozen=True)
class PythonDependency:
    name: str
    exact_version: str
    direct_reference: str | None
    specifier: str | None
    markers: str | None


def parse_version_from_dist(filename: str, name: str) -> str:
    # Ref: https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode
    normalized_name = re.sub(r'[-_.]+', '-', name).lower().replace('-', '_')

    # Ref: https://packaging.python.org/en/latest/specifications/version-specifiers/#version-specifiers
    if mobj := re.match(rf'{normalized_name}-(?P<version>[^-]+)-', filename):
        return mobj.group('version')

    raise ValueError(f'unable to parse version from distribution filename: {filename}')


def parse_dependency(line: str) -> PythonDependency:
    # Ref: https://packaging.python.org/en/latest/specifications/name-normalization/
    NAME_RE = re.compile(r'^(?P<name>[A-Z0-9](?:[A-Z0-9._-]*[A-Z0-9])?)', re.IGNORECASE)

    line = line.rstrip().removesuffix('\\')
    mobj = NAME_RE.match(line)
    if not mobj:
        raise ValueError(f'unable to parse PythonDependency.name from line:\n    {line}')

    name = mobj.group('name')
    rest = line[len(name) :].lstrip()
    specifier_or_direct_reference, _, markers = map(str.strip, rest.partition(';'))
    specifier, _, direct_reference = map(str.strip, specifier_or_direct_reference.partition('@'))

    exact_version = None
    if ',' not in specifier and specifier.startswith('=='):
        exact_version = specifier[2:]

    # Ref: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
    if direct_reference and not exact_version:
        filename = urllib.parse.urlparse(direct_reference).path.rpartition('/')[2]
        if filename.endswith(('.tar.gz', '.whl')):
            exact_version = parse_version_from_dist(filename, name)

    if not exact_version:
        raise ValueError(f'unable to parse PythonDependency.exact_version from line:\n    {line}')

    return PythonDependency(
        name=name,
        exact_version=exact_version,
        direct_reference=direct_reference or None,
        specifier=specifier or None,
        markers=markers or None,
    )


def package_diff_dict(old_dict: dict[str, str], new_dict: dict[str, str]) -> PythonUpdateResult:
    """
    @param old_dict: Dictionary w/ package names as keys and old package versions as values
    @param new_dict: Dictionary w/ package names as keys and new package versions as values
    @returns         Dictionary w/ package names as keys and tuples of (old_ver, new_ver) as values
    """
    ret_dict: PythonUpdateResult = {}

    for name, new_version in new_dict.items():
        if name not in old_dict:
            ret_dict[name] = (None, new_version)
            continue

        old_version = old_dict[name]
        if new_version != old_version:
            ret_dict[name] = (old_version, new_version)

    for name, old_version in old_dict.items():
        if name not in new_dict:
            ret_dict[name] = (old_version, None)

    return ret_dict


def get_lock_packages(lock: dict[str, typing.Any]) -> dict[str, str]:
    return {package['name']: package['version'] for package in lock['package'] if package.get('version')}


type PyprojectTable = dict[str, str | bool | int | float] | dict[str, list[str]]


def get_dependencies(pyproject_toml: dict[str, typing.Any]) -> PyprojectTable:
    return pyproject_toml['project']['dependencies']


def get_extras(pyproject_toml: dict[str, typing.Any], *, resolve: bool = True) -> PyprojectTable:
    project_table = pyproject_toml['project']
    extras = project_table['optional-dependencies']
    if not resolve:
        return extras

    project_name = project_table['name']
    recursive_pattern = re.compile(rf'{project_name}\[(?P<extra_name>[^]]+)\]')

    def yield_deps_from_extra(extra):
        for dep in extra:
            if mobj := recursive_pattern.fullmatch(dep):
                yield from extras[mobj.group('extra_name')]
            else:
                yield dep

    return {extra_name: list(yield_deps_from_extra(extra)) for extra_name, extra in extras.items()}


def get_groups(pyproject_toml: dict[str, typing.Any], *, resolve: bool = True) -> PyprojectTable:
    groups = pyproject_toml['dependency-groups']
    if not resolve:
        return groups

    def yield_deps_from_group(group):
        for dep in group:
            if isinstance(dep, dict):
                yield from yield_deps_from_group(groups[dep['include-group']])
            else:
                yield dep

    return {group_name: list(yield_deps_from_group(group)) for group_name, group in groups.items()}


def _generate_table_lines(
    table_name: str,
    table_dict: PyprojectTable,
) -> collections.abc.Iterator[str]:
    SUPPORTED_TYPES = (str, bool, int, float, list)

    yield f'[{table_name}]\n'
    for name, value in table_dict.items():
        if not isinstance(value, SUPPORTED_TYPES):
            raise TypeError(
                f'expected {"/".join(t.__name__ for t in SUPPORTED_TYPES)} value, got {type(value).__name__}'
            )

        if not isinstance(value, list):
            yield f'{name} = {json.dumps(value)}\n'
            continue

        yield f'{name} = ['
        if value:
            yield '\n'
        for element in value:
            yield '    '
            if isinstance(element, dict):
                yield '{ ' + ', '.join(f'{k} = {json.dumps(v)}' for k, v in element.items()) + ' }'
            else:
                yield f'"{element}"'
            yield ',\n'
        yield ']\n'
    yield '\n'


def replace_toml_table_text(
    toml_text: str,
    table_name: str,
    table_dict: PyprojectTable,
) -> collections.abc.Generator[str]:
    INSIDE = 1
    BEYOND = 2

    state = 0
    for line in toml_text.splitlines(True):
        if state == INSIDE:
            if line == '\n':
                state = BEYOND
            continue
        if line != f'[{table_name}]\n' or state == BEYOND:
            yield line
            continue
        yield from _generate_table_lines(table_name, table_dict)
        state = INSIDE


class PythonProject(Project):
    def __init__(
        self,
        /,
        project_path: pathlib.Path,
        *,
        verbose: bool = False,
    ):
        super().__init__(project_path=project_path, verbose=verbose)

        uv_location = shutil.which('uv')
        if not uv_location:
            raise UVError('uv executable could not be found')
        if not os.access(uv_location, os.F_OK | os.X_OK) or os.path.isdir(uv_location):
            raise UVError(f'unable to execute {uv_location!r}')

        self._uv_exe: str = uv_location
        self._uv_base_args: list[str] = [f'--directory={self.project_path}']

        self.pyproject_path = self.project_path / 'pyproject.toml'
        self._pyproject_text: str | None = None

        self.lockfile_path = self.project_path / 'uv.lock'
        self._lockfile_text: str | None = None

    def load_lockfile_text(self, /, *, refresh: bool = False) -> str | None:
        if not self.lockfile_path.is_file():
            return None

        if refresh or self._lockfile_text is None:
            self._lockfile_text = self.lockfile_path.read_text(encoding='utf-8')

        return self._lockfile_text

    def parse_lockfile_toml(self, /, *, refresh: bool = False) -> dict[str, typing.Any]:
        lockfile_toml = self.load_lockfile_text(refresh=refresh)
        if lockfile_toml is None:
            return {}

        return tomllib.loads(lockfile_toml)

    def load_pyproject_text(self, /, *, refresh: bool = False) -> str:
        if refresh or self._pyproject_text is None:
            self._pyproject_text = self.pyproject_path.read_text(encoding='utf-8')

        return self._pyproject_text

    def parse_pyproject_toml(self, /, *, refresh: bool = False) -> dict[str, typing.Any]:
        return tomllib.loads(self.load_pyproject_text(refresh=refresh))

    def write_pyproject_text(self, /, pyproject_text: str):
        # invalidate cached pyproject
        self._pyproject_text = None
        self.pyproject_path.write_text(pyproject_text)

    def replace_pyproject_toml_table_and_write(
        self,
        /,
        pyproject_text: str,
        table_name: str,
        table_dict: PyprojectTable,
    ):
        # invalidate cached pyproject
        self._pyproject_text = None

        with self.pyproject_path.open(mode='w') as f:
            f.writelines(replace_toml_table_text(pyproject_text, table_name, table_dict))

    def uv(
        self,
        /,
        *args: str,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> list[str]:
        cmd = [self._uv_exe, *self._uv_base_args, *args]

        if self.verbose:
            env_vars = [f'{k}={shlex.quote(v)}' for k, v in (env or {}).items() if k.startswith('UV_')]
            print(' '.join(('[uv]', *env_vars, shlex.join(cmd))), file=sys.stderr)

        # invalidate cached lockfile
        self._lockfile_text = None

        try:
            output = subprocess.run(
                cmd,
                input=stdin,
                env=env,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise UVError(error)

        return output.splitlines()

    def uv_export(
        self,
        /,
        *,
        extras: list[str] | None = None,
        groups: list[str] | None = None,
        prune_packages: list[str] | None = None,
        omit_packages: list[str] | None = None,
        bare: bool = False,
        output_file: pathlib.Path | None = None,
    ) -> list[str]:
        return self.uv(
            'export',
            '--no-python-downloads',
            '--quiet',
            '--no-progress',
            '--color=never',
            '--format=requirements.txt',
            '--frozen',
            '--refresh',
            '--no-emit-project',
            '--no-default-groups',
            '--no-header',
            *(f'--extra={extra}' for extra in (extras or [])),
            *(f'--group={group}' for group in (groups or [])),
            *(f'--prune={package}' for package in (prune_packages or [])),
            *(f'--no-emit-package={package}' for package in (omit_packages or [])),
            *(['--no-annotate', '--no-hashes'] if bare else []),
            *([f'--output-file={output_file.relative_to(self.project_path)}'] if output_file else []),
        )

    def uv_pip_compile(
        self,
        /,
        *args: str,
        input_line: str,
        output_file: pathlib.Path | None = None,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        return self.uv(
            'pip',
            'compile',
            '--no-python-downloads',
            '--quiet',
            '--no-progress',
            '--color=never',
            '--format=requirements.txt',
            '--refresh',
            '--generate-hashes',
            '--no-strip-markers',
            '--no-header',
            '--universal',
            *args,
            *([f'--output-file={output_file.relative_to(self.project_path)}'] if output_file else []),
            '-',  # Read from stdin
            stdin=f'{input_line}\n',
            env=env,
        )


class PythonDependenciesUpdater(DependenciesUpdater):
    def __init__(
        self,
        /,
        project: PythonProject,
        gh: GitHubAPICaller,
    ):
        super().__init__(project=project, gh=gh)
        self.project_path = self.project.project_path
        self.pyproject_path = self.project.pyproject_path
        self.lockfile_path = self.project.lockfile_path
        self.uv = self.project.uv
        self.uv_export = self.project.uv_export
        self.uv_pip_compile = self.project.uv_pip_compile
        self.load_pyproject_text = self.project.load_pyproject_text
        self.parse_pyproject_toml = self.project.parse_pyproject_toml
        self.load_lockfile_text = self.project.load_lockfile_text
        self.parse_lockfile_toml = self.project.parse_lockfile_toml
        self.write_pyproject_text = self.project.write_pyproject_text
        self.replace_pyproject_toml_table_and_write = self.project.replace_pyproject_toml_table_and_write

    def get_exclude_newer_packages(self, /) -> dict[str, str | bool]:
        pyproject_toml = self.parse_pyproject_toml()
        if (
            (tool := pyproject_toml.get('tool'))
            and isinstance(tool, dict)
            and (uv := tool.get('uv'))
            and isinstance(uv, dict)
            and (excludes := uv.get('exclude-newer-package'))
            and isinstance(excludes, dict)
        ):
            return excludes

        return {}

    def _get_last_cooldown_timestamp(self, /) -> str | None:
        lockfile_toml = self.parse_lockfile_toml()
        if (
            (options := lockfile_toml.get('options'))
            and isinstance(options, dict)
            and (last_cooldown_timestamp := options.get('exclude-newer'))
            and isinstance(last_cooldown_timestamp, str)
        ):
            return last_cooldown_timestamp

        return None

    def _get_verify_env(self, /, verify: bool, upgrade_only: str | None) -> dict[str, str] | None:
        if not verify or not upgrade_only or upgrade_only not in self.get_exclude_newer_packages():
            return None

        # If only verifying or only upgrading packages that are cooldown-exempt,
        # then use the previous cooldown timestamp that was recorded in uv.lock
        if last_cooldown_timestamp := self._get_last_cooldown_timestamp():
            return {
                **os.environ,
                'UV_EXCLUDE_NEWER': last_cooldown_timestamp,
            }

        return None

    def update(
        self,
        /,
        *,
        upgrade_only: str | None = None,
        verify: bool = False,
    ) -> tuple[set[pathlib.Path], PythonUpdateResult]:
        # Stash original lockfile for package diff-ing post-update
        og_lockfile_toml = self.parse_lockfile_toml(refresh=True)

        updated_paths: set[pathlib.Path] = set()

        pre_upgrade_data = self._pre_upgrade(updated_paths, upgrade_only=upgrade_only, verify=verify)

        env = self._get_verify_env(verify=verify, upgrade_only=upgrade_only)

        # Upgrade packages in lockfile
        upgrade_arg = f'--upgrade-package={upgrade_only}' if upgrade_only else '--upgrade'
        self.uv('lock', upgrade_arg, env=env)
        updated_paths.add(self.lockfile_path)

        all_updates = package_diff_dict(
            get_lock_packages(og_lockfile_toml) if og_lockfile_toml else {},
            get_lock_packages(self.parse_lockfile_toml(refresh=True)),
        )

        self._post_upgrade(
            pre_upgrade_data,
            updated_paths=updated_paths,
            all_updates=all_updates,
            env=env,
            upgrade_arg=upgrade_arg,
            upgrade_only=upgrade_only,
            verify=verify,
        )

        return updated_paths, all_updates

    def _pre_upgrade(
        self,
        /,
        updated_paths: set[pathlib.Path],
        *,
        upgrade_only: str | None,
        verify: bool,
    ):
        """To be optionally implemented by subclasses.

        Runs before `uv lock` is executed or any changes have been to any of the project files.

        Receives an `updated_paths` set and the same keyword-only arguments as the update() method.

        Can add `pathlib.Path`s to the `updated_paths` set as necessary.

        Can return any data needed to be passed to the _post_uv_lock_hook() method.
        """
        return None

    def _post_upgrade(
        self,
        pre_upgrade_data: typing.Any,
        /,
        *,
        updated_paths: set[pathlib.Path],
        all_updates: PythonUpdateResult,
        env: dict[str, str] | None,
        upgrade_arg: str,
        upgrade_only: str | None,
        verify: bool,
    ):
        """To be optionally implemented by subclasses.

        Runs after `uv lock` is executed and after the PythonUpdateResult has been populated.

        Receives the `pre_upgrade_data` returned from _pre_upgrade() as a positional-only argument.

        Also receives all variables assigned in the update() method as keyword-only arguments.

        Can add `pathlib.Path`s to the `updated_paths` set as necessary.

        Can mutate the `all_updates` PythonUpdateResult dict as necessary.
        """
        pass

    def _generate_report(
        self,
        /,
        all_updates: PythonUpdateResult,
    ) -> collections.abc.Iterator[str]:
        yield 'package | old | new | diff | changelog'
        yield '--------|-----|-----|------|----------'
        for package, (old, new) in sorted(all_updates.items()):
            if package in PYTHON_PACKAGES:
                github_info = PYTHON_PACKAGES[package]
                changelog = ''

            else:
                project_urls = call_pypi_api(package)['info']['project_urls']
                github_info = next(
                    (mobj.groupdict() for url in project_urls.values() if (mobj := GITHUB_URL_RE.match(url))),
                    {},
                )
                changelog = next(
                    (
                        url
                        for key, url in project_urls.items()
                        if key.lower().startswith(('change', 'history', 'release '))
                    ),
                    '',
                )
                if changelog:
                    name = urllib.parse.urlparse(changelog).path.rstrip('/').rpartition('/')[2] or 'changelog'
                    changelog = f'[{name}](<{changelog}>)'

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
                    md_new = f'[{md_new}](<{github_url}/releases/tag/{new_tag}>)'
                if old_tag:
                    md_old = f'[{md_old}](<{github_url}/releases/tag/{old_tag}>)'
                if new_tag and old_tag:
                    compare = f'[`{old_tag}...{new_tag}`](<{github_url}/compare/{old_tag}...{new_tag}>)'

            yield ' | '.join((
                f'[**`{package}`**](<https://pypi.org/project/{package}>)',
                md_old,
                md_new,
                compare,
                changelog,
            ))

    def _make_pull_request_description(
        self,
        /,
        all_updates: PythonUpdateResult,
    ) -> str:
        return '\n'.join((
            f'{BOT_BEGIN_HTML_TAG}\n',
            *self._generate_report(all_updates),
            f'\n{BOT_END_HTML_TAG}\n\n',
        ))

    def parse_results(
        self,
        /,
        all_updates: PythonUpdateResult,
        *,
        commit_prefix: str | None = None,
        commit_addendum: str | None = None,
    ) -> tuple[str, str]:
        """Returns a tuple of the pull request description and the merge commit message"""

        return (
            self._make_pull_request_description(all_updates),
            make_commit_message(all_updates, prefix=commit_prefix, addendum=commit_addendum),
        )
