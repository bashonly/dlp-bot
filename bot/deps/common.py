from __future__ import annotations

import collections.abc
import pathlib


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
    ):
        """Update the project's dependencies.

        Should return a tuple of a set with all updated paths and a dict with results data.
        """
        raise NotImplementedError('this method must be implemented by subclasses')

    def parse_results(
        self,
        /,
        all_updates,
        **kwargs,
    ):
        """Parse the update results and generate text for PRs and commits.

        Required positional argument(s):

        @param all_updates:     the dict of result data that was returned from update()

        Should return a tuple of the pull request description string and commit message string.
        """
        raise NotImplementedError('this method must be implemented by subclasses')

    def get_special_update_function(self, /, value: str) -> collections.abc.Callable:
        """To be re-implemented by subclasses.

        Should return a function/lambda/method that performs the special update procedure.

        The returned function should itself return a set with all updated paths.
        """
        return lambda: set()
