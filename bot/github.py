from __future__ import annotations

import collections.abc
import dataclasses
import itertools
import json
import pathlib
import re
import sys
import time
import types
import typing

from bot.utils import (
    BaseAPICaller,
    BotError,
    filter_dict,
)

GITHUB_URL_RE = re.compile(r'https://github\.com/(?P<owner>[0-9a-zA-Z_-]+)/(?P<repo>[0-9a-zA-Z_-]+)')


class GitHubError(BotError):
    pass


@dataclasses.dataclass(frozen=True)
class BaseBranch:
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        if cls == BaseBranch:
            raise TypeError('cannot instantiate base class')
        return super().__new__(cls)

    def __post_init__(self):
        for slot in self.__slots__:
            value = getattr(self, slot)
            if not isinstance(value, str):
                raise TypeError(f'{type(self).__name__}.{slot} expects a string, got {type(value).__name__!r}')
            if not value:
                raise ValueError(f'{type(self).__name__}.{slot} value cannot be empty')

    def __str__(self):
        return f'{self.owner}:{self.branch}'

    @property
    def label(self, /):
        return str(self)


@dataclasses.dataclass(frozen=True)
class RelativeBranch(BaseBranch):
    __slots__ = ('branch', 'owner')

    owner: str
    branch: str


@dataclasses.dataclass(frozen=True)
class AbsoluteBranch(BaseBranch):
    # GitHub supports this label pattern since 2024
    # Ref: https://github.com/github/docs/issues/34381
    __slots__ = ('branch', 'owner', 'repo')

    owner: str
    repo: str
    branch: str

    @property
    def full_label(self, /):
        return f'{self.owner}:{self.repo}:{self.branch}'


def parse_branch_compare_label(label: str) -> tuple[str, str | None, str]:
    # "branch compare label" is our name for the labels GitHub uses when comparing across forks
    # e.g. yt-dlp:master...bashonly:feature
    # https://docs.github.com/en/rest/commits/commits?apiVersion=2026-03-10#compare-two-commits
    owner, _, repo_and_branch = label.partition(':')
    repo, _, branch = repo_and_branch.rpartition(':')
    return owner, repo or None, branch


def make_absolute_branch(label: str, repo: str | None = None) -> AbsoluteBranch:
    owner, parsed_repo, branch = parse_branch_compare_label(label)
    repo = repo or parsed_repo
    if not repo or not isinstance(repo, str):
        raise ValueError('make_absolute_branch requires a repo value')

    return AbsoluteBranch(owner=owner, repo=repo, branch=branch)


def upgrade_branch(branch: RelativeBranch | AbsoluteBranch, repo: str) -> AbsoluteBranch:
    return AbsoluteBranch(owner=branch.owner, repo=repo, branch=branch.branch)


class GitHubAPICaller(BaseAPICaller):
    _API_BASE_URL = 'https://api.github.com/'
    _NOTE_PREFIX = 'api'

    def __init__(
        self,
        /,
        *,
        retries: int = 3,
        timeout: int = 5,
        verbose: bool = False,
        user_agent: str = 'dlp-bot',
        github_token: str | None = None,
    ):
        super().__init__(
            base_url=self._API_BASE_URL,
            retries=retries,
            timeout=timeout,
            verbose=verbose,
            user_agent=user_agent,
            note_prefix=self._NOTE_PREFIX,
            custom_exception=GitHubError,
        )
        self._github_token = github_token

    @property
    def headers(self) -> dict[str, str]:
        return filter_dict({
            **super().headers,
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {self._github_token}' if self._github_token else None,
            'X-GitHub-Api-Version': '2026-03-10',
        })

    def call(
        self,
        /,
        path: str,
        *,
        query: dict[str, str | None] | None = None,
        body: dict[str, str | bool | int | float] | None = None,
        headers: dict[str, str] | None = None,
        method: str | None = None,
        status_check: list[int] | None = None,
    ):
        return self._fetch_json(
            path,
            query=query,
            data=json.dumps(body, separators=(',', ':')).encode() if body else None,
            headers=filter_dict({
                **self.headers,
                'Content-Type': 'application/json' if body else None,
                **(headers or {}),
            }),
            method=method,
            status_check=status_check,
        )

    def paginator(
        self,
        /,
        func: types.MethodType,
        *args: str,
        searches: list[dict[str, str | bool | int | float | list]] | None = None,
        **kwargs: str | bool | None,
    ) -> collections.abc.Iterator[dict[str, typing.Any]]:
        """Yield pages from any GithubAPICaller.list_* method

        `searches` is a list of dicts with key/value pairs to filter the results by.
        The generator will yield matches until all searches are found or result pages are exhausted.
        If a `searches` dict value is a list, it works like a logical OR for its contained values.
        """
        func_name = func.__name__
        assert func_name.startswith('list_'), f'{func_name} does not return a list'
        assert hasattr(func, '__self__'), f'{func_name} is not an instance method'
        assert isinstance(func.__self__, GitHubAPICaller), f'cannot use {func_name} with paginator'

        if searches:
            requirements = searches.copy()
        else:
            requirements = []

        def filter_func(
            filter_pairs: dict[str, str | bool | int | float | list],
        ) -> collections.abc.Callable[[dict[str, typing.Any]], bool]:
            def inner_func(
                input_dict: dict[str, typing.Any],
            ) -> bool:
                if all(
                    input_dict.get(k) in v if isinstance(v, list) else input_dict.get(k) == v
                    for k, v in filter_pairs.items()
                ):
                    if filter_pairs in requirements:
                        requirements.remove(filter_pairs)
                    return True
                return False

            return inner_func

        for page in itertools.count(1):
            kwargs['page'] = str(page)
            results = func(*args, **kwargs)
            if not results:
                return

            if searches:
                for search in searches:
                    yield from filter(filter_func(search), results)
                if not requirements:
                    return
            else:
                yield from results

    def paginated_results(
        self,
        /,
        *args,
        **kwargs,
    ) -> list[dict[str, typing.Any]]:
        return list(self.paginator(*args, **kwargs))

    # Repositories: https://docs.github.com/en/rest/repos/repos?apiVersion=2026-03-10

    def get_repository(self, /, owner: str, repo: str):
        """Get a repository

        Ref: https://docs.github.com/en/rest/repos/repos?apiVersion=2026-03-10#get-a-repository

        @param owner:                   repository owner
        @param repo:                    repository name
        @returns                        dict of info about the repository
        """
        return self.call(f'/repos/{owner}/{repo}')

    def list_repository_tags(
        self,
        /,
        owner: str,
        repo: str,
        *,
        per_page: str | None = None,
        page: str | None = None,
    ):
        """List repository tags

        Ref: https://docs.github.com/en/rest/repos/repos?apiVersion=2026-03-10#list-repository-tags

        @param owner:                   repository owner
        @param repo:                    repository name
        @param per_page:                (optional) number of results per page (default: 30)
        @param page:                    (optional) page number (default: 1)
        @returns                        list of the repository's tags
        """
        return self.call(f'/repos/{owner}/{repo}/tags', query={'per_page': per_page, 'page': page})

    # Repositories => Forks: https://docs.github.com/en/rest/repos/forks?apiVersion=2026-03-10

    def create_fork(
        self,
        /,
        owner: str,
        repo: str,
        *,
        organization: str | None = None,
        name: str | None = None,
        default_branch_only: bool | None = None,
    ):
        """Create a fork

        Ref: https://docs.github.com/en/rest/repos/forks?apiVersion=2026-03-10#create-a-fork

        @param owner:                   owner of the repository to fork
        @param repo:                    name of the repository to fork
        @param organization:            (optional) fork into this organization instead of account
        @param name:                    (optional) name of the created fork repository
        @param default_branch_only:     (optional) fork only with the default branch if True
        @returns                        dict of info about the fork
        """
        return self.call(
            f'/repos/{owner}/{repo}/forks',
            body=filter_dict({
                'organization': organization,
                'name': name,
                'default_branch_only': default_branch_only,
            }),
            method='POST',
        )

    # Releases: https://docs.github.com/en/rest/releases/releases?apiVersion=2026-03-10

    def list_releases(
        self,
        /,
        owner: str,
        repo: str,
        *,
        per_page: str | None = None,
        page: str | None = None,
    ):
        """List releases

        Ref: https://docs.github.com/en/rest/releases/releases?apiVersion=2026-03-10#list-releases

        @param owner:                   repository owner
        @param repo:                    repository name
        @param per_page:                (optional) number of results per page (default: 30)
        @param page:                    (optional) page number (default: 1)
        @returns                        list of the repository's releases
        """
        return self.call(f'/repos/{owner}/{repo}/releases', query={'per_page': per_page, 'page': page})

    def get_latest_release(self, /, owner: str, repo: str):
        """Get the latest release

        Ref: https://docs.github.com/en/rest/releases/releases?apiVersion=2026-03-10#get-the-latest-release

        @param owner:                   repository owner
        @param repo:                    repository name
        @returns                        dict of info about the latest release
        """
        return self.call(f'/repos/{owner}/{repo}/releases/latest')

    def get_release_by_tag_name(self, /, owner: str, repo: str, tag_name: str, *, allow_miss: bool = False):
        """Get a release by tag name

        Ref: https://docs.github.com/en/rest/releases/releases?apiVersion=2026-03-10#get-a-release-by-tag-name

        @param owner:                   repository owner
        @param repo:                    repository name
        @param tag_name:                tag name
        @param allow_miss:              (optional) if True, return empty dict instead of error 404
        @returns                        dict of info about the release for the given tag
        """
        result = self.call(
            f'/repos/{owner}/{repo}/releases/tags/{tag_name}', status_check=[404] if allow_miss else None
        )

        if result is False:
            return {}

        return result

    def create_release(
        self,
        /,
        owner: str,
        repo: str,
        tag_name: str,
        *,
        target_commitish: str | None = None,
        name: str | None = None,
        body: str | None = None,
        draft: bool | None = None,
        prerelease: bool | None = None,
        generate_release_notes: bool | None = None,
        make_latest: str | None = None,
    ):
        """Create a release

        Ref: https://docs.github.com/en/rest/releases/releases?apiVersion=2026-03-10#create-a-release

        @param owner:                   repository owner
        @param repo:                    repository name
        @param tag_name:                tag name
        @param target_commitish:        (optional) commitish where to create the tag from
        @param name:                    (optional) the name of the release
        @param body:                    (optional) the body/description of the release
        @param draft:                   (optional) bool: True for draft (default: False)
        @param prerelease:              (optional) bool: True for prerelease (default: False)
        @param generate_release_notes:  (optional) bool: generate name/description (default: False)
        @param make_latest:             (optional) str: one of 'true' (default), 'false', 'legacy'
        @returns                        dict of info about the created release
        """
        return self.call(
            f'/repos/{owner}/{repo}/releases',
            body=filter_dict({
                'tag_name': tag_name,
                'target_commitish': target_commitish,
                'name': name,
                'body': body,
                'draft': draft,
                'prerelease': prerelease,
                'generate_release_notes': generate_release_notes,
                'make_latest': make_latest,
            }),
            method='POST',
        )

    # Pull requests: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10

    def create_pull_request(
        self,
        /,
        owner: str,
        repo: str,
        head: str,
        base: str,
        *,
        head_repo: str | None = None,
        title: str | None = None,
        body: str | None = None,
        maintainer_can_modify: bool | None = None,
        draft: bool | None = None,
    ):
        """Create a pull request

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#create-a-pull-request

        @param owner:                   repository owner
        @param repo:                    repository name
        @param head:                    the pull request head's {owner}:{branch}
        @param base:                    the name of the branch you want the changes pulled into
        @param head_repo:               (optional) head repo, only required if a fork on same org
        @param title:                   (optional) the title of the new pull request
        @param body:                    (optional) the body/description of the new pull request
        @param maintainer_can_modify:   (optional) if maintainers can edit the PR
        @param draft:                   (optional) if the pull request is a draft
        @returns                        dict of info about the created pull request
        """
        if owner == head.partition(':')[0] and not head_repo:
            raise ValueError('head_repo is required if the repo is a fork in the same organization')

        return self.call(
            f'/repos/{owner}/{repo}/pulls',
            body=filter_dict({
                'title': title,
                'body': body,
                'head': head,
                'head_repo': head_repo,
                'base': base,
                'maintainer_can_modify': maintainer_can_modify,
                'draft': draft,
            }),
            method='POST',
        )

    def update_pull_request(
        self,
        /,
        owner: str,
        repo: str,
        pull_number: str,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        base: str | None = None,
        maintainer_can_modify: bool | None = None,
    ):
        """Update a pull request

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#update-a-pull-request

        @param owner:                   repository owner
        @param repo:                    repository name
        @param pull_number:             the number that identifies the pull request
        @param title:                   (optional) the title of the pull request
        @param body:                    (optional) the body/description of the pull request
        @param state:                   (optional) state of the PR: 'open' or 'closed'
        @param base:                    (optional) name of branch for the changes to be pulled into
        @param maintainer_can_modify:   (optional) if maintainers can edit the PR
        @returns                        dict of info about the updated pull request
        """
        return self.call(
            f'/repos/{owner}/{repo}/pulls/{pull_number}',
            body=filter_dict({
                'title': title,
                'body': body,
                'state': state,
                'base': base,
                'maintainer_can_modify': maintainer_can_modify,
            }),
            method='PATCH',
        )

    def list_pull_requests(
        self,
        /,
        owner: str,
        repo: str,
        *,
        state: str | None = None,
        head: str | None = None,
        base: str | None = None,
        sort: str | None = None,
        direction: str | None = None,
        per_page: str | None = None,
        page: str | None = None,
    ):
        """List pull requests

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#list-pull-requests

        @param owner:                   repository owner
        @param repo:                    repository name
        @param state:                   (optional) filter by state: 'open' (default), 'closed', or 'all'
        @param head:                    (optional) filter by the PR's head {owner}:{branch}
        @param base:                    (optional) filter by the base branch name
        @param sort:                    (optional) 'created', 'updated', 'popularity', 'long-running'
        @param direction:               (optional) sort by: 'asc', 'desc'
        @param per_page:                (optional) number of results per page (default: 30)
        @param page:                    (optional) page number (default: 1)
        @returns                        list of PRs for {owner}/{repo} matching the filters
        """
        if state and state not in ('open', 'closed', 'all'):
            raise ValueError(f'Invalid state value: {state}')
        if sort and sort not in ('created', 'updated', 'popularity', 'long-running'):
            raise ValueError(f'Invalid sort value: {sort}')
        if direction and direction not in ('asc', 'desc'):
            raise ValueError(f'Invalid direction value: {direction}')

        return self.call(
            f'/repos/{owner}/{repo}/pulls',
            query={
                'state': state,
                'head': head,
                'base': base,
                'sort': sort,
                'direction': direction,
                'per_page': per_page,
                'page': page,
            },
        )

    def get_pull_request(self, /, owner: str, repo: str, pull_number: str):
        """Get a pull request

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#get-a-pull-request

        @param owner:                   repository owner
        @param repo:                    repository name
        @param pull_number:             the number that identifies the pull request
        @returns                        dict of info about the queried pull request
        """
        return self.call(f'/repos/{owner}/{repo}/pulls/{pull_number}')

    def check_if_pull_request_merged(self, /, owner: str, repo: str, pull_number: str) -> bool:
        """Check if a pull request has been merged

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#check-if-a-pull-request-has-been-merged

        @param owner:                   repository owner
        @param repo:                    repository name
        @param pull_number:             the number that identifies the pull request
        @returns                        boolean: True if merged, False if not merged
        """
        return self.call(f'/repos/{owner}/{repo}/pulls/{pull_number}/merge', status_check=[404])

    def merge_pull_request(
        self,
        /,
        owner: str,
        repo: str,
        pull_number: str,
        *,
        commit_title: str | None = None,
        commit_message: str | None = None,
        sha: str | None = None,
        merge_method: str | None = None,
    ):
        """Merge a pull request

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#merge-a-pull-request

        @param owner:                   repository owner
        @param repo:                    repository name
        @param pull_number:             the number that identifies the pull request
        @param commit_title:            (optional) subject line of the commit message
        @param commit_message:          (optional) the body of the commit message
        @param sha:                     (optional) SHA that PR head must match to allow merge
        @param merge_method:            (optional) one of 'merge', 'squash', 'rebase'
        @returns                        dict with 'sha' (str), 'merged' (bool), 'message' (str)
        """
        if merge_method and merge_method not in ('merge', 'squash', 'rebase'):
            raise ValueError(f'Invalid merge_method value: {merge_method}')

        return self.call(
            f'/repos/{owner}/{repo}/pulls/{pull_number}/merge',
            body=filter_dict({
                'commit_title': commit_title,
                'commit_message': commit_message,
                'sha': sha,
                'merge_method': merge_method,
            }),
            method='PUT',
        )

    def update_pull_request_branch(
        self,
        /,
        owner: str,
        repo: str,
        pull_number: str,
        *,
        expected_head_sha: str | None = None,
    ) -> bool:
        """Update a pull request branch

        Ref: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#update-a-pull-request-branch

        @param owner:                   repository owner
        @param repo:                    repository name
        @param pull_number:             the number that identifies the pull request
        @param expected_head_sha:       (optional) SHA that PR head must match to allow merge
        @returns                        bool: True if successful, False if SHA didn't match PR head
        """
        return bool(
            self.call(
                f'/repos/{owner}/{repo}/pulls/{pull_number}/update-branch',
                body=filter_dict({'expected_head_sha': expected_head_sha}),
                method='PUT',
                status_check=[422] if expected_head_sha else None,
            )
        )

    # Git database => References: https://docs.github.com/en/rest/git/refs?apiVersion=2026-03-10

    def get_ref(self, /, owner: str, repo: str, ref: str) -> bool:
        """Get a reference

        Ref: https://docs.github.com/en/rest/git/refs?apiVersion=2026-03-10#get-a-reference

        @param owner:                   repository owner
        @param repo:                    repository name
        @param ref:                     git reference (i.e. heads/{branch} or tags/{tag})
        @returns                        dict of info about the ref
        """
        return self.call(f'/repos/{owner}/{repo}/git/refs/{ref}')

    def get_branch_by_name(self, /, owner: str, repo: str, branch_name: str):
        """Get a branch (by name)

        @param owner:                   repository owner
        @param repo:                    repository name
        @param branch_name:             branch name
        @returns                        dict of info about the branch
        """
        return self.get_ref(owner, repo, f'heads/{branch_name}')

    def get_tag_by_name(self, /, owner: str, repo: str, tag_name: str):
        """Get a tag (by name)

        @param owner:                   repository owner
        @param repo:                    repository name
        @param tag_name:                tag name
        @returns                        dict of info about the tag
        """
        return self.get_ref(owner, repo, f'tags/{tag_name}')

    def delete_ref(self, /, owner: str, repo: str, ref: str) -> bool:
        """Delete a reference

        Ref: https://docs.github.com/en/rest/git/refs?apiVersion=2026-03-10#delete-a-reference

        @param owner:                   repository owner
        @param repo:                    repository name
        @param ref:                     git reference (i.e. heads/{branch} or tags/{tag})
        @returns                        boolean: True if deleted, False if not deleted
        """
        return self.call(f'/repos/{owner}/{repo}/git/refs/{ref}', method='DELETE', status_check=[409, 422])

    def delete_branch_by_name(self, /, owner: str, repo: str, branch_name: str) -> bool:
        """Delete a branch (by name)

        @param owner:                   repository owner
        @param repo:                    repository name
        @param branch_name:             branch name
        @returns                        boolean: True if deleted, False if not deleted
        """
        return self.delete_ref(owner, repo, f'heads/{branch_name}')

    def delete_tag_by_name(self, /, owner: str, repo: str, tag_name: str) -> bool:
        """Delete a tag (by name)

        @param owner:                   repository owner
        @param repo:                    repository name
        @param tag_name:                tag name
        @returns                        boolean: True if deleted, False if not deleted
        """
        return self.delete_ref(owner, repo, f'tags/{tag_name}')

    # Git database => Tags: https://docs.github.com/en/rest/git/tags?apiVersion=2026-03-10

    def get_tag_by_sha(self, /, owner: str, repo: str, tag_sha: str):
        """Get a tag by the tag's SHA

        Ref: https://docs.github.com/en/rest/git/tags?apiVersion=2026-03-10

        @param owner:                   repository owner
        @param repo:                    repository name
        @param tag_sha:                 the tag's SHA hash
        @returns                        dict of the tag's signature verification object
        """
        return self.call(f'/repos/{owner}/{repo}/git/tags/{tag_sha}')

    # Branches: https://docs.github.com/en/rest/branches/branches?apiVersion=2026-03-10

    def merge_branch(
        self,
        /,
        owner: str,
        repo: str,
        base: str,
        head: str,
        *,
        commit_message: str | None = None,
    ):
        """Merge a branch

        Ref: https://docs.github.com/en/rest/branches/branches?apiVersion=2026-03-10#merge-a-branch

        @param owner:                   repository owner
        @param repo:                    repository name
        @param base:                    name of the base branch that the head will be merged into
        @param head:                    the head to merge; can be a branch name or a commit SHA1
        @param commit_message:          (optional) commit message for the merge commit
        @returns                        dict of info about the resulting merge commit
        """
        return self.call(
            f'/repos/{owner}/{repo}/merges',
            body=filter_dict({
                'base': base,
                'head': head,
                'commit_message': commit_message,
            }),
            method='POST',
        )


class GitHubWebFetcher(BaseAPICaller):
    _WEB_BASE_URL = 'https://github.com/'
    _NOTE_PREFIX = 'web'

    def __init__(
        self,
        /,
        *,
        retries: int = 3,
        timeout: int = 5,
        verbose: bool = False,
        user_agent: str = 'dlp-bot',
    ):
        super().__init__(
            base_url=self._WEB_BASE_URL,
            retries=retries,
            timeout=timeout,
            verbose=verbose,
            user_agent=user_agent,
            note_prefix=self._NOTE_PREFIX,
            custom_exception=GitHubError,
        )

    @classmethod
    def from_api_instance(
        cls,
        /,
        api: GitHubAPICaller,
    ) -> GitHubWebFetcher:
        return cls(
            retries=api.retries,
            timeout=api.timeout,
            verbose=api.verbose,
            user_agent=api.user_agent,
        )

    def fetch(self, /, path: str):
        return self._fetch_json(path, headers=self.headers)

    def fetch_repo(self, /, owner: str, repo: str):
        return self.fetch(f'/{owner}/{repo}')

    def fetch_actions_marketplace(self, /, action_slug: str):
        return self.fetch(f'/marketplace/actions/{action_slug}')

    def fetch_branch_commits(self, /, owner: str, repo: str, sha: str):
        return self.fetch(f'{owner}/{repo}/branch_commits/{sha}')


class GitHubPullRequest:
    def __init__(
        self,
        /,
        base: AbsoluteBranch,
        head: AbsoluteBranch,
        *,
        info: dict[str, typing.Any] | None = None,
        github_token: str | None = None,
        verbose: bool = False,
    ):
        for branch in (base, head):
            if not isinstance(branch, AbsoluteBranch):
                raise TypeError(f'{type(self).__name__} expected an AbsoluteBranchobject, got {type(branch).__name__}')

        self.base = base
        self.head = head

        self.api = GitHubAPICaller(github_token=github_token, verbose=verbose)

        self._title: str | None = None
        self._title_unsaved_changes = False
        self._body: str | None = None
        self._body_unsaved_changes = False
        self._commit_message: str | None = None

        self.created: bool | None = None
        self.merged: bool | None = None
        self.draft: bool | None = None
        self.state: str | None = None

        self._info_last_updated: int = 0
        self._info: dict[str, typing.Any] = {}
        if info is not None:
            self._info.update(info)

        self._update_attributes(initial=True)

    @classmethod
    def from_branches(
        cls,
        /,
        repo: str,
        base: str | RelativeBranch | AbsoluteBranch,
        head: str | RelativeBranch | AbsoluteBranch,
        **kwargs: typing.Any,
    ) -> GitHubPullRequest:
        if isinstance(base, str):
            base = make_absolute_branch(base, repo)
        else:
            base = upgrade_branch(base, repo)

        if isinstance(head, str):
            head = make_absolute_branch(head, repo)
        else:
            head = upgrade_branch(head, repo)

        return cls(base=base, head=head, **kwargs)

    @classmethod
    def from_info(
        cls,
        /,
        info: dict[str, typing.Any],
        **kwargs: typing.Any,
    ) -> GitHubPullRequest:
        return cls(
            base=make_absolute_branch(info['base']['label'], info['base']['repo']['name']),
            head=make_absolute_branch(info['head']['label'], info['head']['repo']['name']),
            info=info,
            **kwargs,
        )

    @classmethod
    def from_number(
        cls,
        /,
        owner: str,
        repo: str,
        number: typing.Any,
        **kwargs: typing.Any,
    ) -> GitHubPullRequest:
        pull_number: str = cls._validate_number(number)
        gh = GitHubAPICaller(**kwargs)

        return cls.from_info(gh.get_pull_request(owner, repo, pull_number), **kwargs)

    @staticmethod
    def _validate_number(number: typing.Any) -> str:
        try:
            return str(int(number))
        except ValueError:
            raise ValueError('expected int or numeric string for pull request number')

    def _update_attributes(self, /, *, initial: bool = False):
        if not self.info:
            return

        self.merged = self.info['merged']
        self.draft = self.info['draft']
        self.state = self.info['state']
        self.created = self.state is not None

        if not self._title_unsaved_changes:
            self._title = self.info['title']
        if not self._body_unsaved_changes:
            self._body = self.info['body']

        if not initial:
            self._info_last_updated = int(time.time())

    @property
    def info(self, /) -> dict[str, typing.Any]:
        return self._info

    @property
    def number(self, /) -> str:
        if not self.info or self.info.get('number') is None:
            raise AttributeError(f'this {type(self).__name__} instance does not yet have a number')

        return self._validate_number(self.info['number'])

    def populate(self, /) -> None:
        if not self.info or self.info.get('number') is None:
            results = self.api.list_pull_requests(
                self.base.owner,
                self.base.repo,
                state='open',
                head=self.head.label,
                base=self.base.branch,
                sort='created',
                direction='desc',
            )
            if not results:
                self.created = False
                self.merged = False
                self.draft = False
                return
            number = str(results[0]['number'])
        else:
            number = self.number

        # we don't want/need to repopulate info more than every 5 seconds
        if self._info_last_updated > int(time.time()) - 5:
            return

        self._info.update(
            self.api.get_pull_request(
                self.base.owner,
                self.base.repo,
                number,
            )
        )
        self._update_attributes()

    def is_created(self, /) -> bool:
        self.populate()
        return bool(self.created)

    def is_open(self, /) -> bool:
        self.populate()
        return self.state == 'open'

    def is_merged(self, /) -> bool:
        if self.merged:
            return True

        if not self.info:
            self.populate()
            return bool(self.merged)

        self.merged = self.api.check_if_pull_request_merged(
            self.base.owner,
            self.base.repo,
            self.number,
        )
        return self.merged

    def create(
        self,
        /,
        title: str | None = None,
        body: str | None = None,
        maintainer_can_modify: bool | None = None,
        draft: bool | None = None,
    ):
        if self.is_created():
            print(f'pull request #{self.number} has already been created', file=sys.stderr)
            return

        self._info.update(
            self.api.create_pull_request(
                self.base.owner,
                self.base.repo,
                self.head.label,
                self.base.branch,
                head_repo=self.head.repo,
                title=self.update_title(title) if title else self.title,
                body=self.update_body(body) if body else self.body,
                maintainer_can_modify=maintainer_can_modify,
                draft=draft,
            )
        )
        self._title_unsaved_changes = False
        self._body_unsaved_changes = False
        self._update_attributes()

    def update(
        self,
        /,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        base: str | None = None,
        maintainer_can_modify: bool | None = None,
    ):
        if not self.is_created():
            print('unable to update pull request as it has not yet been created', file=sys.stderr)
            return

        self._info.update(
            self.api.update_pull_request(
                self.base.owner,
                self.base.repo,
                self.number,
                title=self.update_title(title) if title else self.title,
                body=self.update_body(body) if body else self.body,
                state=state,
                base=base,
                maintainer_can_modify=maintainer_can_modify,
            )
        )
        self._title_unsaved_changes = False
        self._body_unsaved_changes = False
        self._update_attributes()

    def create_or_update(
        self,
        /,
        *,
        title: str | None = None,
        body: str | None = None,
        maintainer_can_modify: bool | None = None,
        draft: bool | None = None,
    ) -> None:
        if self.is_created():
            print(f'PR #{self.number} already exists, updating its info', file=sys.stderr)
            self.update(
                title=title,
                body=body,
                maintainer_can_modify=maintainer_can_modify,
            )
        else:
            self.create(
                title=title,
                body=body,
                maintainer_can_modify=maintainer_can_modify,
                draft=draft,
            )

    def close(self, /) -> None:
        if not self.is_open():
            print('unable to reopen pull request as it has already been merged', file=sys.stderr)
            return

        if result := self.update(state='closed'):
            self._info.update(result)
            self._update_attributes()

    def reopen(self, /) -> None:
        if self.is_open():
            print('unable to reopen pull request as it is already open', file=sys.stderr)
            return

        if self.is_merged():
            print('unable to reopen pull request as it has already been merged', file=sys.stderr)
            return

        if result := self.update(state='open'):
            self._info.update(result)
            self._update_attributes()

    def merge(
        self,
        /,
        commit_title: str,
        commit_message: str,
        *,
        expected_head_sha: str | None = None,
        merge_method: str = 'squash',
    ):
        if not self.is_open():
            print('unable to merge pull request as it is not open', file=sys.stderr)
            return

        return self.api.merge_pull_request(
            self.head.owner,
            self.head.repo,
            self.number,
            commit_title=commit_title,
            commit_message=commit_message,
            sha=expected_head_sha,
            merge_method=merge_method,
        )

    def sync_branch(self, /, *, expected_head_sha: str | None = None) -> bool:
        if not self.is_open():
            print('unable to sync pull request branch as it is not open', file=sys.stderr)
            return False

        if self.api.update_pull_request_branch(
            self.head.owner,
            self.head.repo,
            self.number,
            expected_head_sha=expected_head_sha,
        ):
            return True

        print(f'failed to sync branch: {self.head.label}', file=sys.stderr)
        return False

    def delete_branch(self, /) -> bool:
        if self.api.delete_branch_by_name(self.head.owner, self.head.repo, self.head.branch):
            self.state = 'closed'
            return True

        print(f'unable to delete branch: {self.head.label}', file=sys.stderr)
        return False

    @property
    def title(self, /) -> str | None:
        return self._title

    def update_title(self, /, text: str | None) -> str | None:
        self._title_unsaved_changes = True
        self._title = self._parse_subject_and_body_from_message(text)[0]
        return self._title

    def load_title_from_patch_file(self, /, path: pathlib.Path) -> str | None:
        return self.update_title(self._parse_message_from_patch_file(path))

    @property
    def body(self, /) -> str | None:
        return self._body

    def update_body(self, /, text: str | None) -> str | None:
        self._body_unsaved_changes = True
        self._body = text or None
        return self._body

    def append_to_body(self, /, text: str, *, separator: str = '\n\n') -> str | None:
        return self.update_body(separator.join(filter(None, [self._body, text])))

    def load_body_from_patch_file(self, /, path: pathlib.Path) -> str | None:
        return self.update_body(self._parse_subject_and_body_from_message(self._parse_message_from_patch_file(path))[1])

    @property
    def commit_message(self, /) -> str | None:
        return self._commit_message

    @property
    def commit_message_subject(self, /) -> str | None:
        return self._parse_subject_and_body_from_message(self._commit_message)[0]

    @property
    def commit_message_body(self, /) -> str | None:
        return self._parse_subject_and_body_from_message(self._commit_message)[1]

    def update_commit_message(self, /, text: str | None) -> str | None:
        self._commit_message = text or None
        if text and not self.title:
            self.update_title(text)

        return self._commit_message

    def load_commit_message_from_patch_file(self, /, path: pathlib.Path) -> str | None:
        return self.update_commit_message(self._parse_message_from_patch_file(path))

    def _yield_message_lines_from_patch_file(
        self,
        /,
        path: pathlib.Path,
    ) -> collections.abc.Iterator[str]:
        SUBJECT_PREFIX = 'Subject: '
        TERMINATE_LINE = '---\n'

        in_message = False
        with path.open('r') as f:
            for line in f:
                if line.startswith(SUBJECT_PREFIX):
                    in_message = True
                    line = line.removeprefix(SUBJECT_PREFIX)
                if line == TERMINATE_LINE:
                    return
                if in_message:
                    yield line

    def _parse_message_from_patch_file(self, /, path: pathlib.Path) -> str:
        return ''.join(self._yield_message_lines_from_patch_file(path))

    def _parse_subject_and_body_from_message(
        self,
        /,
        commit_message: str | None,
    ) -> tuple[str | None, str | None]:
        if commit_message is None:
            return None, None

        lines = commit_message.splitlines()
        if not lines:
            return None, None

        return lines[0] or None, '\n'.join(lines[2:]) or None
