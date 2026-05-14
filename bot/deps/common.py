from __future__ import annotations

import contextlib
import pathlib
import re

from bot.git import Commit
from bot.utils import BotError

try:
    import yaml
except ImportError:
    yaml = None

type DependencyDiffType = tuple[str, str] | tuple[str, None] | tuple[None, str] | tuple[str | None, str | None]
type DependenciesUpdateResult = dict[str, DependencyDiffType]


def package_diff_dict(old_dict: dict[str, str], new_dict: dict[str, str]) -> DependenciesUpdateResult:
    """
    @param old_dict: Dictionary w/ package names as keys and old package versions as values
    @param new_dict: Dictionary w/ package names as keys and new package versions as values
    @returns         Dictionary w/ package names as keys and tuples of (old_ver, new_ver) as values
    """
    ret_dict: DependenciesUpdateResult = {}

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


def denormalized_tags(tag: str, *prefixes: str) -> list[str]:
    tags = [tag]
    # De-normalize calver tags like 2024.1.1 back to 2024.01.01
    if re.match(r'2[0-9]{3}\.[1-9]\.', tag) or re.match(r'2[0-9]{3}\.[0-9]{2}\.[1-9][^0-9]*', tag):
        with contextlib.suppress(ValueError):
            year, month, day = map(int, tag.split('.'))
            tags.append(f'{year}.{month:02d}.{day:02d}')

    return tags + [f'{prefix}{t}' for t in tags for prefix in prefixes]


def make_commit_message(
    all_updates: DependenciesUpdateResult,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
    serialized_data: str | None = None,
) -> str:
    addendum = f'\n\n{addendum}\n' if addendum else '\n'
    serialized_data = f'\n---\n\n{serialized_data}\n' if serialized_data else ''

    if len(all_updates) > 1:
        return ''.join((
            make_commit_title(all_updates, prefix=prefix),
            '\n\n',
            make_commit_body(all_updates),
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


def make_commit_title(all_updates: DependenciesUpdateResult, *, prefix: str | None = None) -> str:
    count = len(all_updates)
    return f'{prefix or ""}Update {count} dependenc{"ies" if count > 1 else "y"}'


def make_commit_body(all_updates: DependenciesUpdateResult) -> str:
    return '\n'.join(sorted(make_commit_line(package, old, new) for package, (old, new) in all_updates.items()))


def make_commit_line(package: str, old: str | None, new: str | None, *, prefix: str = '* ') -> str:
    if old is None:
        return f'{prefix}Add {package} {new}'

    if new is None:
        return f'{prefix}Remove {package} {old}'

    return f'{prefix}Bump {package} {old} => {new}'


class Project:
    """Base class for all projects

    @param project_path:    a pathlib.Path instance pointing to the root directory of the project
    @param verbose:         boolean value that enables verbose logging if True
    """

    def __init__(
        self,
        /,
        project_path: pathlib.Path,
        **kwargs,
    ):
        self.project_path = pathlib.Path(project_path).expanduser().resolve()
        self.project_path.mkdir(parents=True, exist_ok=True)


class DependenciesUpdater:
    """Base class for all dependencies updaters

    Required positional argument(s):

    @param project:         an instance of Project or a Project subclass
    """

    _UPDATES_KEY = 'dependencies'

    def __init__(
        self,
        /,
        project,
        **kwargs,
    ):
        self.project = project

    def update(
        self,
        /,
        **kwargs,
    ) -> tuple[set[pathlib.Path], DependenciesUpdateResult]:
        """Update the project's dependencies.

        Should return a tuple of a set with all updated paths and a dict with results data.
        """
        raise NotImplementedError('this method must be implemented by subclasses')

    def parse_results(
        self,
        /,
        all_updates: DependenciesUpdateResult,
        existing_commits: list[Commit],
        **kwargs,
    ) -> tuple[str, str, str]:
        """Parse the update results and generate text for PRs and commits.

        Required positional argument(s):

        @param all_updates:         the dict of result data that was returned from update()

        @param existing_commits:    a list of bot.git.Commit objects from previous update(s)

        Should return a tuple of pull request description, commit message, and merge commit message.
        """
        raise NotImplementedError('this method must be implemented by subclasses')

    def serialize_results(self, /, updates: DependenciesUpdateResult) -> str:
        if yaml is None:
            raise BotError('the pyyaml package (yaml library) is required')

        return yaml.safe_dump({self._UPDATES_KEY: updates}, sort_keys=False)

    def deserialize_results(self, /, text: str) -> DependenciesUpdateResult:
        if yaml is None:
            raise BotError('the pyyaml package (yaml library) is required')

        parsed_yaml = yaml.safe_load(text) or {}
        serialized_updates = parsed_yaml.get(self._UPDATES_KEY, {})
        updates: DependenciesUpdateResult = {}

        for package, (old, new) in serialized_updates.items():
            updates[package] = (old, new)

        return updates

    def get_previous_updates(self, /, commits: list[Commit]) -> DependenciesUpdateResult:
        previous_updates: DependenciesUpdateResult = {}
        oldest: dict[str, str | None] = {}
        newest: dict[str, str | None] = {}

        for commit in sorted(commits, key=lambda c: c.timestamp):
            updates = self.deserialize_results(commit.body.partition('\n---\n')[2])
            for package, (old, new) in updates.items():
                if package not in oldest:
                    oldest[package] = old
                newest[package] = new

        for package, oldest_version in oldest.items():
            previous_updates[package] = (oldest_version, newest[package])

        return previous_updates

    def reconcile_updates(
        self,
        /,
        previous_updates: DependenciesUpdateResult,
        new_updates: DependenciesUpdateResult,
    ) -> DependenciesUpdateResult:
        result: DependenciesUpdateResult = {}

        for package, (old, new) in previous_updates.items():
            if package not in new_updates:
                result[package] = (old, new)
            else:
                result[package] = (old, new_updates[package][1])

        for package, (old, new) in new_updates.items():
            if package not in result:
                result[package] = (old, new)

        return result
