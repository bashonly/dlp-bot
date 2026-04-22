from __future__ import annotations

import pathlib

from bot.github import GitHubAPICaller


class Project:
    """Base class for all projects

    @param project_path:    a pathlib.Path instance pointing to the root directory of the project
    @param verbose:         boolean value that enables verbose logging if True
    """

    def __init__(
        self,
        /,
        project_path: pathlib.Path,
        *,
        verbose: bool = False,
    ):
        self.project_path = pathlib.Path(project_path).expanduser().resolve()
        self.project_path.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose


class DependenciesUpdater:
    """Base class for all dependencies updaters

    @param project:         an instance of Project or a Project subclass
    @param gh:              an instance of bot.github.GitHubAPICaller
    """

    def __init__(
        self,
        /,
        project,
        gh: GitHubAPICaller,
    ):
        self.project = project
        self.gh = gh

    def update(self, /, *args, **kwargs):
        """Update the project's dependencies"""
        raise NotImplementedError('this method must be implemented by subclasses')

    def parse_results(self, /, *args, **kwargs):
        """Parse update()'s result and return a tuple of the PR description and commit message"""
        raise NotImplementedError('this method must be implemented by subclasses')
