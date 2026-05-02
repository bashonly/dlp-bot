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
from bot.knowledge import (
    ACTIONS,
    BOT_BEGIN_HTML_TAG,
    BOT_END_HTML_TAG,
)
from bot.utils import (
    SHA1_PATTERN,
    BotError,
    VerificationError,
    is_sha1,
    parse_owner_and_repo,
)

try:
    import yaml
except ImportError:
    yaml = None


WORKFLOWS_DIRECTORY = '.github/workflows'

USES_RE_TMPL = r'\buses:\s+(?P<path>{label}(?:/[\w-]+)?)@(?P<sha>{sha})\s+#\s*(?P<tag>v?[0-9]+(?:\.[0-9]+)*)'


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

    def __str__(self):
        return f'{self.owner}/{self.repo}'

    def __lt__(self, other):
        return str(self) < other

    def __gt__(self, other):
        return str(self) > other


@dataclasses.dataclass(frozen=True)
class ActionPin:
    action: Action
    sha: str
    tag: str


type ActionsUpdateResult = dict[Action, tuple[ActionPin, ActionPin]]

ACTIONLINT_ACTION = Action(owner='rhysd', repo='actionlint', default_branch='main')
ACTIONLINT_ASSET_TMPL = 'actionlint_{version}_linux_amd64.tar.gz'
ACTIONLINT_RE = re.compile(r"""(?x)
    (?P<before>ACTIONLINT_VERSION:\s+(?P<q>["\']))
    (?P<tag>(?!(?P=q)).+)
    (?P<inbetween>(?P=q)\s+ACTIONLINT_SHA256SUM:\s+["\']?)
    (?P<sha>[0-9a-f]{64})""")


def parse_gha_uses_value(uses_value: str) -> tuple[str, str]:
    action_value, _, commit_sha = uses_value.partition('@')
    return action_value, commit_sha


def release_is_too_hot(release: dict[str, typing.Any], cooldown: dt.datetime | None) -> bool:
    if cooldown is None:
        return False

    timestamp = release['published_at'] if release['immutable'] else release['updated_at']

    return dt.datetime.fromisoformat(timestamp) > cooldown


def get_tag_from_comment(action: Action, sha: str, workflow_text: str) -> str:
    mobj = re.search(USES_RE_TMPL.format(label=re.escape(str(action)), sha=sha), workflow_text)
    if not mobj:
        raise WorkflowError(f'Unable to find tag comment for "{action}" in workflow')

    return mobj.group('tag')


def make_pull_request_description(workflows: list[Workflow], all_updates: ActionsUpdateResult) -> str:
    return '\n'.join((
        f'{BOT_BEGIN_HTML_TAG}\n',
        *generate_actions_report(all_updates),
        '',
        *generate_workflows_report(workflows),
        f'\n{BOT_END_HTML_TAG}\n\n',
    ))


def make_bulk_commit_message(
    workflows: list[Workflow],
    all_updates: ActionsUpdateResult,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
) -> str:
    return ''.join((
        make_bulk_commit_title(workflows, all_updates, prefix=prefix),
        '\n\n',
        make_bulk_commit_body(all_updates),
        f'\n\n{addendum}\n' if addendum else '\n',
    ))


def make_bulk_commit_title(
    workflows: list[Workflow],
    all_updates: ActionsUpdateResult,
    *,
    prefix: str | None = None,
) -> str:
    workflows_count = len([workflow for workflow in workflows if workflow.updated_actions])
    actions_count = len(all_updates)
    return ''.join((
        prefix or '',
        f'Update {actions_count} action',
        's' if actions_count > 1 else '',
        f' in {workflows_count} workflow',
        's' if workflows_count > 1 else '',
    ))


def make_bulk_commit_body(all_updates: ActionsUpdateResult) -> str:
    return '\n'.join(sorted(make_action_commit_line(action, old, new) for action, (old, new) in all_updates.items()))


def make_incremental_commit_message(
    action: Action,
    old: ActionPin,
    new: ActionPin,
    *,
    prefix: str | None = None,
    addendum: str | None = None,
) -> str:
    return ''.join((
        make_action_commit_line(action, old, new, prefix=prefix or ''),
        f'\n\n{addendum}\n' if addendum else '\n',
    ))


def make_action_commit_line(action: Action, old: ActionPin, new: ActionPin, *, prefix: str = '* ') -> str:
    return f'{prefix}Bump {action} {old.tag} => {new.tag}'


def generate_workflows_report(workflows: list[Workflow]) -> collections.abc.Iterator[str]:
    yield 'workflow | updates'
    yield '---------|--------'
    for workflow in sorted(workflows):
        if not workflow.updated_actions:
            continue
        updates = ', '.join(f'`{action}`' for action in workflow.updated_actions)
        yield f'**`{workflow}`** | {updates}'


def generate_actions_report(all_updates: ActionsUpdateResult) -> collections.abc.Iterator[str]:
    yield 'action | old | new | diff'
    yield '-------|-----|-----|-----'
    for action, (old, new) in sorted(all_updates.items()):
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
        github_url = f'https://github.com/{action}'

        yield ' | '.join((
            f'[**`{action}`**](<{github_url}>)',
            f'[{md_old}](<{github_url}/releases/tag/{old.tag}>)',
            f'[{md_new}](<{github_url}/releases/tag/{new.tag}>)',
            f'[`{old.sha[:7]}...{new.sha[:7]}`](<{github_url}/compare/{old.sha}...{new.sha}>)',
        ))


class Workflow:
    def __init__(self, /, path: pathlib.Path):
        self.path = path.resolve()
        self._text = path.read_text(encoding='utf-8')
        self._unwritten = False
        self.updated_actions: ActionsUpdateResult = {}
        self.needed_updates: set[Action] = set()

    def __str__(self):
        return self.path.name

    def __lt__(self, other):
        return str(self) < other

    def __gt__(self, other):
        return str(self) > other

    @property
    def text(self, /) -> str:
        return self._text

    def update_text(self, /, text: str, *, require_update: bool = False):
        if text != self._text:
            self._text = text
            self._unwritten = True
        elif require_update:
            raise WorkflowError(f'failed to update "{self}"')

    def update_pins(self, /, old: ActionPin, new: ActionPin):
        if old.action not in self.needed_updates:
            raise WorkflowError(f'unexpected attempt to update "{old.action}" for "{self}"')

        self.needed_updates.remove(old.action)
        self.update_text(
            re.sub(
                USES_RE_TMPL.format(label=re.escape(str(old.action)), sha=SHA1_PATTERN),
                rf'uses: \g<path>@{new.sha}  # {new.tag}',
                self.text,
            ),
            require_update=True,
        )
        self.updated_actions[old.action] = (old, new)

    def write(self, /):
        if self._unwritten:
            self.path.write_text(self.text, encoding='utf-8')
            self._unwritten = False

    def parse(self) -> dict[typing.Any, typing.Any]:
        if yaml is None:
            raise WorkflowError('the pyyaml package (yaml library) is required')

        parsed = yaml.safe_load(self.text)

        if not isinstance(parsed, dict):
            raise WorkflowError(f'unrecognized workflow file format for "{self}"')
        if 'jobs' not in parsed:
            raise WorkflowError(f'no jobs found in workflow for "{self}"')

        return parsed

    # temporary actionlint hack
    def _update_actionlint(self, /, old: ActionPin, new: ActionPin):
        if old.action not in self.needed_updates:
            raise WorkflowError(f'unexpected attempt to update "{old.action}" for "{self}"')

        self.needed_updates.remove(old.action)
        self.update_text(
            ACTIONLINT_RE.sub(rf'\g<before>{new.tag}\g<inbetween>{new.sha}', self.text),
            require_update=True,
        )
        self.updated_actions[old.action] = (old, new)


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
            parse_owner_and_repo(key): Action(**action_dict) for key, action_dict in ACTIONS.items()
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
        local_path: pathlib.Path,
        repo_owner: str,
        repo_name: str,
        *,
        github_token: str | None = None,
        verbose: bool = False,
        **kwargs,
    ) -> ActionsUpdater:
        return cls(
            git=Git(local_path, verbose=verbose),
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
        if not is_sha1(commit_sha):
            return None
        owner, repo = parse_owner_and_repo(full_action_name)
        if owner in ('.', '.github'):
            return None
        if owner == self.repo_owner and repo == self.repo_name:
            return None
        return uses_value

    def get_action(self, /, github_action_path: str) -> Action:
        owner, repo = parse_owner_and_repo(github_action_path)
        if (owner, repo) in self._actions_cache:
            return self._actions_cache[(owner, repo)]

        print(f'Getting info about {owner}/{repo}', file=sys.stderr)
        banners = self.web.fetch_repo(owner, repo)['payload']['codeViewRepoRoute']['overview']['banners']
        action_slug = banners.get('actionSlug')
        default_branch = self.api.get_repository(owner, repo)['default_branch']
        action = Action(owner, repo, default_branch=default_branch, action_slug=action_slug)
        self._actions_cache[(owner, repo)] = action

        return action

    def get_action_and_current_pin(self, /, uses_value: str, text: str) -> tuple[Action, ActionPin]:
        github_action_path, current_sha = parse_gha_uses_value(uses_value)
        action = self.get_action(github_action_path)
        current_tag = get_tag_from_comment(action, current_sha, text)

        return action, ActionPin(action=action, sha=current_sha, tag=current_tag)

    def parse_actions_from_workflow(
        self,
        /,
        workflow: Workflow,
    ) -> dict[Action, ActionPin]:
        actions = {}

        jobs = workflow.parse()['jobs']
        if not isinstance(jobs, dict):
            raise WorkflowError(f'unrecognized jobs format in "{workflow}"')

        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                raise WorkflowError(f'unrecognized job format for "{job_name}" in "{workflow}"')

            if 'uses' in job and self._validate_uses_value(job['uses']):
                action, current_pin = self.get_action_and_current_pin(job['uses'], workflow.text)
                actions[action] = current_pin

            elif 'steps' in job:
                steps = job['steps']
                if not isinstance(steps, list):
                    raise WorkflowError(f'unrecognized steps format for job "{job_name}" in "{workflow}"')

                for step_number, step in enumerate(steps, 1):
                    if not isinstance(step, dict):
                        raise WorkflowError(f'unrecognized step format for "{job_name}/{step_number}" in "{workflow}"')

                    if 'uses' in step and self._validate_uses_value(step['uses']):
                        action, current_pin = self.get_action_and_current_pin(step['uses'], workflow.text)
                        actions[action] = current_pin

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
        if not is_sha1(sha):
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
        if action in self._latest_cache:
            return self._latest_cache[action]

        print(f'Getting latest eligible release for {action}', file=sys.stderr)

        latest_tag = None
        latest_release = None

        if action.action_slug:
            latest_tag = self.web.fetch_actions_marketplace(
                action.action_slug,
            )['payload']['releaseData']['latestRelease']['tagName']

        # Only the first page of releases should be sufficient
        releases = self.api.list_releases(action.owner, action.repo)

        for release in releases:
            if release['prerelease'] or release['draft']:
                continue
            if latest_tag and release['tag_name'] == latest_tag:
                if release_is_too_hot(release, self._exclude_newer):
                    print(
                        f'the latest release for {action} is being skipped per cooldown policy: {latest_tag}',
                        file=sys.stderr,
                    )
                    latest_tag = None
                    continue
                latest_release = release
                break
            if not latest_tag:
                target = release['target_commitish']
                if target != action.default_branch and not is_sha1(target):
                    continue
                if release_is_too_hot(release, self._exclude_newer):
                    print(
                        f'release "{release["tag_name"]}" for {action} is being skipped per cooldown policy',
                        file=sys.stderr,
                    )
                    continue
                latest_release = release
                break
        else:
            raise ActionError(f'unable to get latest eligible release for action: {action}')

        latest_tag, latest_sha = self.get_tag_and_sha_from_release(action.owner, action.repo, latest_release)

        # For verification
        if latest_tag not in self.web.fetch_branch_commits(action.owner, action.repo, latest_sha)['tags']:
            raise VerificationError(f'SHA not found in {action}: {latest_sha}')

        # temporary actionlint hack
        if action == ACTIONLINT_ACTION:
            latest_tag = latest_tag.removeprefix('v')
            latest_sha = next(
                asset['digest'].removeprefix('sha256:')
                for asset in release['assets']
                if asset['name'] == ACTIONLINT_ASSET_TMPL.format(version=latest_tag)
                and asset['digest'].startswith('sha256:')
            )

        latest_pin = ActionPin(action, sha=latest_sha, tag=latest_tag)
        self._latest_cache[action] = latest_pin
        return latest_pin

    def update(
        self,
        /,
        *,
        commit_type: str | None = None,
        export_patches: str | pathlib.Path | None = None,
        commit_prefix: str | None = None,
        commit_addendum: str | None = None,
        verify: bool = False,
    ) -> tuple[list[Workflow], ActionsUpdateResult]:
        if commit_type not in (None, 'bulk', 'incremental'):
            raise ValueError(f'invalid commit_type value: {commit_type}')

        starting_point = self.git.bot_rev_parse('HEAD')
        gha_path = self.git.repo_path / WORKFLOWS_DIRECTORY
        workflows = [Workflow(path) for path in itertools.chain(gha_path.glob('*.yml'), gha_path.glob('*.yaml'))]
        all_updates = {}

        for workflow in workflows:
            actions = self.parse_actions_from_workflow(workflow)
            for action, current_pin in actions.items():
                if action in workflow.updated_actions:
                    continue

                latest_pin = self.get_latest_action_pin(action)
                if current_pin.sha == latest_pin.sha:
                    continue

                workflow.needed_updates.add(action)
                all_updates[action] = (current_pin, latest_pin)

            # temporary actionlint hack
            lint_old_pin = self._parse_for_actionlint_pin(workflow)
            if not lint_old_pin:
                continue
            lint_new_pin = self.get_latest_action_pin(ACTIONLINT_ACTION)
            if lint_old_pin == lint_new_pin:
                continue
            workflow.needed_updates.add(ACTIONLINT_ACTION)
            all_updates[ACTIONLINT_ACTION] = (lint_old_pin, lint_new_pin)

        updated_paths = set()

        if commit_type == 'incremental':
            for action, (old, new) in all_updates.items():
                for workflow in workflows:
                    if action in workflow.needed_updates:
                        # temporary actionlint hack
                        if action == ACTIONLINT_ACTION:
                            workflow._update_actionlint(old, new)
                        else:
                            workflow.update_pins(old, new)

                        workflow.write()
                        updated_paths.add(workflow.path)

                commit_msg = make_incremental_commit_message(
                    action, old, new, prefix=commit_prefix, addendum=commit_addendum
                )
                if not verify:
                    self.git.bot_commit(commit_msg, updated_paths)
                updated_paths.clear()

        else:  # Minimize I/O for bulk commit
            for workflow in workflows:
                needed_updates = workflow.needed_updates.copy()
                for action in needed_updates:
                    # temporary actionlint hack
                    if action == ACTIONLINT_ACTION:
                        workflow._update_actionlint(*all_updates[action])
                    else:
                        workflow.update_pins(*all_updates[action])

                workflow.write()
                updated_paths.add(workflow.path)

            commit_msg = make_bulk_commit_message(
                workflows, all_updates, prefix=commit_prefix, addendum=commit_addendum
            )
            if not verify:
                self.git.bot_commit(commit_msg, updated_paths)

        if export_patches and not verify:
            self.git.bot_patches(starting_point, export_patches)

        return workflows, all_updates

    # temporary actionlint hack
    def _parse_for_actionlint_pin(self, /, workflow: Workflow) -> ActionPin | None:
        mobj = ACTIONLINT_RE.search(workflow.text)
        if not mobj:
            return None
        return ActionPin(ACTIONLINT_ACTION, sha=mobj.group('sha'), tag=mobj.group('tag'))

    def parse_results(
        self,
        /,
        workflows: list[Workflow],
        all_updates: ActionsUpdateResult,
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
