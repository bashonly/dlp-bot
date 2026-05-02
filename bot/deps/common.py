from __future__ import annotations

import contextlib
import pathlib
import re

type DependenciesUpdateResult = dict[str, tuple[str, str] | tuple[str, None] | tuple[None, str]]


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


def denormalized_tags(tag: str) -> list[str]:
    tags = [tag]
    # De-normalize calver tags like 2024.1.1 back to 2024.01.01
    if re.match(r'2[0-9]{3}\.[1-9]\.', tag) or re.match(r'2[0-9]{3}\.[0-9]{2}\.[1-9][^0-9]*', tag):
        with contextlib.suppress(ValueError):
            year, month, day = map(int, tag.split('.'))
            tags.append(f'{year}.{month:02d}.{day:02d}')

    return tags + [f'v{t}' for t in tags]


def make_commit_message(
    all_updates: DependenciesUpdateResult,
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
        **kwargs,
    ) -> tuple[str, str]:
        """Parse the update results and generate text for PRs and commits.

        Required positional argument(s):

        @param all_updates:     the dict of result data that was returned from update()

        Should return a tuple of the pull request description string and commit message string.
        """
        raise NotImplementedError('this method must be implemented by subclasses')
