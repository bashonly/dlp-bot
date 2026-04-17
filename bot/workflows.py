from __future__ import annotations

import collections.abc
import dataclasses
import datetime as dt
import itertools
import pathlib
import re
import sys
import typing

from bot.git import Git
from bot.github import (
    GitHubAPICaller,
    GitHubPullRequest,
    GitHubWebFetcher,
)
from bot.knowledge import ACTIONS
from bot.utils import (
    BotError,
    is_sha,
    parse_owner_and_repo,
)

try:
    import yaml
except ImportError:
    yaml = None


WORKFLOWS_DIRECTORY = '.github/workflows'


class ActionError(BotError):
    pass


class WorkflowError(BotError):
    pass


@dataclasses.dataclass(frozen=True)
class Action:
    owner: str
    repo: str
    default_branch: str
    action_slug: str | None = None


@dataclasses.dataclass(frozen=True)
class ActionPin:
    action: Action
    sha: str
    tag: str


type WorkflowResults = dict[pathlib.Path, dict[str, ActionPin]]
type AllUpdates = dict[Action, tuple[ActionPin, ActionPin]]


def parse_gha_uses_value(uses_value: str) -> tuple[str, str]:
    action_value, _, commit_sha = uses_value.partition('@')
    return action_value, commit_sha


def release_is_too_hot(release: dict[str, typing.Any], cooldown: dt.datetime | None) -> bool:
    if cooldown is None:
        return False

    timestamp = release['published_at'] if release['immutable'] else release['updated_at']

    return dt.datetime.fromisoformat(timestamp) > cooldown


def get_pin_and_comment(uses_pin: str, workflow_text: str) -> tuple[str, str]:
    mobj = re.search(rf'\buses:\s+{re.escape(uses_pin)}\s+#\s*(?P<tag>v?[0-9]+(?:\.[0-9]+)*)', workflow_text)
    if not mobj:
        raise WorkflowError(f'Unable to find tag comment for "{uses_pin}" in workflow')

    return uses_pin, mobj.group('tag')


def update_pins_in_workflow_text(
    full_action_name: str,
    latest_pin: ActionPin,
    workflow_text: str,
    workflow_path: pathlib.Path,
) -> str:
    replaced_text = re.sub(
        rf'\buses:\s+{re.escape(full_action_name)}@[0-9a-fA-F]{{40}}(?:\s+#.+)?',
        f'uses: {full_action_name}@{latest_pin.sha}  # {latest_pin.tag}',
        workflow_text,
    )

    if replaced_text == workflow_text:
        raise WorkflowError(f'Failed to replace action pin in: {workflow_path}')

    return replaced_text


def make_pull_request_description(
    workflows: WorkflowResults,
    all_updates: AllUpdates,
) -> str:
    return '\n'.join(
        (
            '<!-- BEGIN dlp-bot generated section -->\n',
            *generate_actions_report(all_updates),
            '',
            *generate_workflows_report(workflows),
            '\n<!-- END dlp-bot generated section -->\n\n',
        )
    )


def make_bulk_commit_message(
    workflows: WorkflowResults,
    all_updates: AllUpdates,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
) -> str:
    return '\n\n'.join(
        (
            make_bulk_commit_title(workflows, all_updates, prefix=prefix),
            make_bulk_commit_body(all_updates),
            f'{addendum or ""}\n',
        )
    )


def make_bulk_commit_title(
    workflows: WorkflowResults,
    all_updates: AllUpdates,
    *,
    prefix: str | None = None,
) -> str:
    workflows_count = len(list(filter(None, workflows.values())))
    actions_count = len(all_updates)
    return ''.join(
        (
            prefix or '',
            f'Update {actions_count} action',
            's' if actions_count > 1 else '',
            f' in {workflows_count} workflow',
            's' if workflows_count > 1 else '',
        )
    )


def make_bulk_commit_body(all_updates: AllUpdates) -> str:
    return '\n'.join(sorted(make_commit_line(action, old, new) for action, (old, new) in all_updates.items()))


def make_incremental_commit_message(
    action: Action,
    old: ActionPin,
    new: ActionPin,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
) -> str:
    return '\n\n'.join(
        (
            make_commit_line(action, old, new, prefix=prefix or ''),
            f'{addendum or ""}\n',
        )
    )


def make_commit_line(action: Action, old: ActionPin, new: ActionPin, *, prefix: str = '* ') -> str:
    return f'{prefix}Bump {action.owner}/{action.repo} {old.tag} => {new.tag}'


def generate_workflows_report(
    workflows: WorkflowResults,
) -> collections.abc.Iterator[str]:
    slice_val = (len(WORKFLOWS_DIRECTORY.split('/')) + 1) * -1

    yield 'workflow | updates'
    yield '---------|--------'
    for workflow_path, updated_actions in sorted(workflows.items()):
        if not updated_actions:
            continue
        updates = ', '.join(f'`{name}`' for name in updated_actions)
        yield f'**`{"/".join(workflow_path.parts[slice_val:])}`** | {updates}'


def generate_actions_report(
    all_updates: AllUpdates,
) -> collections.abc.Iterator[str]:
    yield 'action | old | new | diff'
    yield '-------|-----|-----|-----'
    for action, (old, new) in sorted(all_updates.items(), key=lambda a: f'{a[0].owner}/{a[0].repo}'):
        md_old = old.tag
        md_new = new.tag
        # bolden and italicize the differing parts
        old_parts = md_old.removeprefix('v').split('.')
        new_parts = md_new.removeprefix('v').split('.')

        offset = None
        for index, (old_part, new_part) in enumerate(zip(old_parts, new_parts, strict=False)):
            if old_part != new_part:
                offset = index
                break

        if offset is not None:
            md_old = '.'.join(old_parts[:offset]) + '.***' + '.'.join(old_parts[offset:]) + '***'
            md_new = '.'.join(new_parts[:offset]) + '.***' + '.'.join(new_parts[offset:]) + '***'

        md_old = ('v' if old.tag.startswith('v') else '') + md_old.lstrip('.')
        md_new = ('v' if new.tag.startswith('v') else '') + md_new.lstrip('.')
        github_url = f'https://github.com/{action.owner}/{action.repo}'

        yield ' | '.join(
            (
                f'[**`{action.owner}/{action.repo}`**](<{github_url}>)',
                f'[{md_old}](<{github_url}/releases/tag/{old.tag}>)',
                f'[{md_new}](<{github_url}/releases/tag/{new.tag}>)',
                f'[`{old.sha[:7]}...{new.sha[:7]}`](<{github_url}/compare/{old.sha}...{new.sha}>)',
            )
        )


class ActionsUpdater:
    def __init__(
        self,
        /,
        git: Git,
        api: GitHubAPICaller,
        web: GitHubWebFetcher,
        repo_owner: str,
        repo_name: str,
        *,
        exclude_newer: dt.datetime | None = None,
    ):
        self.git = git
        self.api = api
        self.web = web
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self._exclude_newer = exclude_newer

        self._latest_cache: dict[Action, ActionPin] = {}
        self._actions_cache: dict[tuple[str, str], Action] = {
            parse_owner_and_repo(key): Action(**action) for key, action in ACTIONS.items()
        }

    @classmethod
    def from_git_and_pr(
        cls,
        /,
        git: Git,
        pr: GitHubPullRequest,
        **kwargs,
    ) -> ActionsUpdater:
        return cls(
            git=git,
            api=pr.api,
            web=GitHubWebFetcher.from_api_instance(pr.api),
            repo_owner=pr.base.owner,
            repo_name=pr.base.repo,
            **kwargs,
        )

    @classmethod
    def from_repo_info(
        cls,
        /,
        local_path: str | pathlib.Path,
        repo_owner: str,
        repo_name: str,
        *,
        github_token: str | None = None,
        verbose: bool = False,
        **kwargs,
    ) -> ActionsUpdater:
        return cls(
            git=Git(str(local_path), verbose=verbose),
            api=GitHubAPICaller(github_token=github_token, verbose=verbose),
            web=GitHubWebFetcher(verbose=verbose),
            repo_owner=repo_owner,
            repo_name=repo_name,
            **kwargs,
        )

    def _validate_uses_value(self, /, uses_value: str) -> str | None:
        if not isinstance(uses_value, str):
            return None
        if '@' not in uses_value:
            return None
        full_action_name, commit_sha = parse_gha_uses_value(uses_value)
        if not is_sha(commit_sha):
            return None
        owner, repo = parse_owner_and_repo(full_action_name)
        if owner in ('.', '.github'):
            return None
        if owner == self.repo_owner and repo == self.repo_name:
            return None
        return uses_value

    def parse_actions_from_workflow(
        self,
        /,
        workflow_path: pathlib.Path,
    ) -> list[tuple[str, str]]:
        if yaml is None:
            raise ImportError('the pyyaml package (yaml library) is required')

        if not workflow_path.is_file():
            raise WorkflowError(f'Invalid input: {workflow_path}')

        workflow_text = workflow_path.read_text(encoding='utf-8')
        workflow_yaml = yaml.safe_load(workflow_text)
        if not isinstance(workflow_yaml, dict):
            raise WorkflowError(f'Unrecognized workflow file format: {workflow_path}')
        if 'jobs' not in workflow_yaml:
            raise WorkflowError(f'No jobs found in workflow: {workflow_path}')

        actions = []

        jobs = workflow_yaml['jobs']
        if not isinstance(jobs, dict):
            raise WorkflowError(f'Unrecognized jobs format: {workflow_path}')

        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                raise WorkflowError(f'Unrecognized job format for "{job_name}": {workflow_path}')

            if 'uses' in job and self._validate_uses_value(job['uses']):
                actions.append(get_pin_and_comment(job['uses'], workflow_text))

            elif 'steps' in job:
                steps = job['steps']
                if not isinstance(steps, list):
                    raise WorkflowError(f'Unrecognized steps format for job "{job_name}": {workflow_path}')
                for step_number, step in enumerate(steps, 1):
                    if not isinstance(step, dict):
                        raise WorkflowError(f'Unrecognized step format for "{job_name}/{step_number}": {workflow_path}')
                    if 'uses' in step and self._validate_uses_value(step['uses']):
                        actions.append(get_pin_and_comment(step['uses'], workflow_text))

        return actions

    def get_tag_and_sha_from_release(
        self,
        /,
        owner: str,
        repo: str,
        release: dict[str, typing.Any],
    ) -> tuple[str, str]:
        tag: str = release['tag_name']
        sha: str = release['target_commitish']

        # Is target_commitish was just a branch name?
        if not is_sha(sha):
            tagged_object = self.api.get_tag_by_name(owner, repo, tag)['object']

            if tagged_object['type'] != 'commit':
                if tagged_object['type'] != 'tag':
                    raise ValueError(f'expected tag object, got {tagged_object["type"]!r}')

                tagged_object = self.api.get_tag_by_sha(owner, repo, tagged_object['sha'])['object']

            if tagged_object['type'] != 'commit':
                raise ValueError(f'expected commit object, got {tagged_object["type"]!r}')

            sha = tagged_object['sha']

        return tag, sha

    def get_latest_action_pin(
        self,
        /,
        action: Action,
    ) -> ActionPin:
        print(f'Getting latest eligible release for {action.owner}/{action.repo}', file=sys.stderr)

        latest_tag = None
        latest_release = None

        if action.action_slug:
            latest_tag = self.web.fetch_actions_marketplace(action.action_slug)['payload']['releaseData'][
                'latestRelease'
            ]['tagName']

        # Only the first page of releases should be sufficient
        releases = self.api.list_releases(action.owner, action.repo)

        for release in releases:
            if release['prerelease'] or release['draft']:
                continue
            if latest_tag and release['tag_name'] == latest_tag:
                if release_is_too_hot(release, self._exclude_newer):
                    print(
                        f'The latest release for {action.owner}/{action.repo} is being skipped '
                        f'per cooldown policy: {latest_tag}',
                        file=sys.stderr,
                    )
                    latest_tag = None
                    continue
                latest_release = release
                break
            if not latest_tag:
                target = release['target_commitish']
                if target != action.default_branch and not is_sha(target):
                    continue
                if release_is_too_hot(release, self._exclude_newer):
                    print(
                        f'Release "{release["tag_name"]}" for {action.owner}/{action.repo} '
                        'is being skipped per cooldown policy',
                        file=sys.stderr,
                    )
                    continue
                latest_release = release
                break
        else:
            raise ActionError(f'Unable to get latest eligible release for action: {action.owner}/{action.repo}')

        latest_tag, latest_sha = self.get_tag_and_sha_from_release(action.owner, action.repo, latest_release)

        # Sanity check
        if latest_tag not in self.web.fetch_branch_commits(action.owner, action.repo, latest_sha)['tags']:
            raise ValueError(f'SHA not found in {action.owner}/{action.repo}: {latest_sha}')

        return ActionPin(action, sha=latest_sha, tag=latest_tag)

    def update(
        self,
        /,
        *,
        commit_type: str | None = None,
        export_patches: str | pathlib.Path | None = None,
        commit_prefix: str | None = None,
        commit_addendum: str | None = None,
    ) -> tuple[WorkflowResults, AllUpdates]:
        if commit_type not in ('bulk', 'incremental'):
            raise ValueError(f'invalid commit_type value: {commit_type}')

        base_path = pathlib.Path(self.git.repo_dir).resolve()
        starting_point = self.git.bot_rev_parse('HEAD')

        gha_path = base_path / WORKFLOWS_DIRECTORY

        workflows: WorkflowResults = {
            workflow_path: {} for workflow_path in itertools.chain(gha_path.glob('*.yml'), gha_path.glob('*.yaml'))
        }

        all_updates = {}

        for workflow_path, current_workflow_updates in workflows.items():
            used_actions = self.parse_actions_from_workflow(workflow_path)

            for uses_value, current_tag in used_actions:
                full_action_name, current_sha = parse_gha_uses_value(uses_value)

                if full_action_name in current_workflow_updates:
                    continue

                owner, repo = parse_owner_and_repo(full_action_name)

                if (owner, repo) in self._actions_cache:
                    action = self._actions_cache[(owner, repo)]
                else:
                    print(f'Getting info about {owner}/{repo}', file=sys.stderr)
                    banners = self.web.fetch_repo(owner, repo)['payload']['codeViewRepoRoute']['overview']['banners']
                    action_slug = banners.get('actionSlug')
                    default_branch = self.api.get_repository(owner, repo)['default_branch']
                    action = Action(owner, repo, default_branch=default_branch, action_slug=action_slug)
                    self._actions_cache[(owner, repo)] = action

                current_pin = ActionPin(action, sha=current_sha, tag=current_tag)

                if action in self._latest_cache:
                    latest_pin = self._latest_cache[action]
                else:
                    latest_pin = self.get_latest_action_pin(action)
                    self._latest_cache[action] = latest_pin

                if current_pin.sha == latest_pin.sha:
                    continue

                current_workflow_updates[full_action_name] = latest_pin
                all_updates[action] = (current_pin, latest_pin)

        updated_paths = set()

        if commit_type == 'incremental':
            for action, (old, new) in all_updates.items():
                for workflow_path, current_workflow_updates in workflows.items():
                    workflow_text = workflow_path.read_text()
                    for full_action_name, latest_pin in current_workflow_updates.items():
                        if (action.owner, action.repo) == parse_owner_and_repo(full_action_name):
                            workflow_text = update_pins_in_workflow_text(
                                full_action_name, latest_pin, workflow_text, workflow_path
                            )

                    workflow_path.write_text(workflow_text)
                    updated_paths.add(workflow_path)

                commit_msg = make_incremental_commit_message(
                    action, old, new, prefix=commit_prefix, addendum=commit_addendum
                )
                self.git.bot_commit(commit_msg, updated_paths)
                updated_paths.clear()

        else:  # Minimize I/O for bulk commit
            for workflow_path, current_workflow_updates in workflows.items():
                workflow_text = workflow_path.read_text()
                for full_action_name, latest_pin in current_workflow_updates.items():
                    workflow_text = update_pins_in_workflow_text(
                        full_action_name, latest_pin, workflow_text, workflow_path
                    )

                workflow_path.write_text(workflow_text)
                updated_paths.add(workflow_path)

            commit_msg = make_bulk_commit_message(
                workflows, all_updates, prefix=commit_prefix, addendum=commit_addendum
            )
            self.git.bot_commit(commit_msg, updated_paths)

        if export_patches:
            self.git.bot_patches(starting_point, export_patches)

        return workflows, all_updates

    def parse_results(
        self,
        /,
        workflows: WorkflowResults,
        all_updates: AllUpdates,
        *,
        commit_prefix: str | None = None,
        commit_addendum: str | None = None,
    ) -> tuple[str, str]:
        """Returns a tuple of the pull request description and the merge commit message"""

        if len(all_updates) > 1:
            commit_message = make_bulk_commit_message(
                workflows,
                all_updates,
                prefix=commit_prefix,
                addendum=commit_addendum,
            )
        else:
            action = next(iter(all_updates))
            commit_message = make_incremental_commit_message(
                action,
                all_updates[action][0],
                all_updates[action][1],
                prefix=commit_prefix,
                addendum=commit_addendum,
            )

        return make_pull_request_description(workflows, all_updates), commit_message
