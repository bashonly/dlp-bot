"""
Update the default user-agent version range used by yt-dlp.
"""

from __future__ import annotations

import argparse
import collections.abc
import os
import pathlib
import sys
import tempfile

from bot.command.common import (
    configure_export_options,
    configure_git_options,
    configure_github_options,
    configure_logging_options,
    configure_remote_target_options,
    configure_update_options,
)
from bot.git import Git, GitError
from bot.github import GitHubPullRequest, RelativeBranch
from bot.knowledge import (
    DEFAULT_HEAD_BRANCHES,
    DEFAULT_HEAD_OWNER,
    GIT_FORGE,
    PULL_REQUEST_TEMPLATES,
    SERVICED_REPOS,
)
from bot.utils import (
    BaseAPICaller,
    BotError,
    SuccessMessage,
    VerificationError,
)

UPDATE_NAME = 'user-agent'

DEFAULT_HEAD = RelativeBranch(owner=DEFAULT_HEAD_OWNER, branch=DEFAULT_HEAD_BRANCHES[UPDATE_NAME])

REPO = 'yt-dlp'

PREFIX = '    CHROME_MAJOR_VERSION_RANGE = '
TARGET_FILE = 'yt_dlp/utils/networking.py'
FLOOR_DIFF = 6


def configure_parser(parser: argparse.ArgumentParser):
    # NB: Do not use type=pathlib.Path in arg parser since it would convert empty arg to Path('.')
    parser.add_argument(
        'directory',
        metavar='DIRECTORY',
        nargs=argparse.OPTIONAL,
        help=(
            'local path to the root of the git working tree. '
            'if not provided and --clone is not used, it will default to the CWD ("."). '
            'if not provided and --clone is used, it will default to a temporary directory'
        ),
    )
    # Add common option groups
    configure_remote_target_options(
        parser,
        default_head_label=DEFAULT_HEAD.label,
    )
    configure_update_options(parser)
    configure_git_options(parser)
    configure_github_options(parser)
    configure_export_options(parser)
    configure_logging_options(parser)


class _GoogleVersionHistoryAPICaller(BaseAPICaller):
    _API_BASE_URL = 'https://versionhistory.googleapis.com/'
    _NOTE_PREFIX = 'googleapis'

    def __init__(self, /, *, verbose: bool = False):
        super().__init__(
            base_url=self._API_BASE_URL,
            verbose=verbose,
            note_prefix=self._NOTE_PREFIX,
        )

    def get_latest_win_chrome_stable_release(self, /):
        return self._fetch_json(
            '/v1/chrome/platforms/win/channels/stable/versions/all/releases',
            query={'filter': 'endtime=none,fraction>=0.5', 'order_by': 'version desc'},
            headers=self.headers,
        )


def _get_old_range_line(module_text: str) -> str:
    for line in module_text.splitlines():
        if not line.startswith(PREFIX):
            continue
        return line

    raise BotError('unable to find user-agent range line')


def _get_old_user_agent_range(range_line: str) -> tuple[int, int]:
    floor, _, ceiling = range_line.removeprefix(PREFIX).removeprefix('(').removesuffix(')').partition(', ')
    return int(floor), int(ceiling)


def _get_new_user_agent_range(*, verbose: bool = False) -> tuple[int, int]:
    api = _GoogleVersionHistoryAPICaller(verbose=verbose)
    info = api.get_latest_win_chrome_stable_release()
    new_ceiling = int(info['releases'][0]['version'].partition('.')[0])
    return new_ceiling - FLOOR_DIFF, new_ceiling


def _replace_user_agent_range(
    module_text: str,
    range_line: str,
    new_range: tuple[int, int],
) -> collections.abc.Generator[str]:
    lines = module_text.splitlines(True)
    for line_number, line in enumerate(lines, start=1):
        if not line.startswith(PREFIX):
            yield line
            continue
        yield f'{PREFIX}{new_range}\n'
        yield from lines[line_number:]
        return


def update_user_agent_range(
    module_path: pathlib.Path,
    *,
    verify: bool = False,
    verbose: bool = False,
) -> str:
    module_text = module_path.read_text()
    range_line = _get_old_range_line(module_text)
    old_range = _get_old_user_agent_range(range_line)
    new_range = _get_new_user_agent_range(verbose=verbose)

    if old_range == new_range:
        raise SuccessMessage('user-agent version range is up-to-date')

    description = f'Bump version range {old_range} => {new_range}'

    if verify:
        print(description)
        raise VerificationError('update verification failed')

    with module_path.open(mode='w') as f:
        f.writelines(_replace_user_agent_range(module_text, range_line, new_range))

    return description


def _real_run(args: argparse.Namespace):
    if not args.directory:
        if args.clone:
            repo_path = pathlib.Path(tempfile.mkdtemp())
        else:
            repo_path = pathlib.Path('.')
    else:
        repo_path = pathlib.Path(args.directory)

    repo_info = SERVICED_REPOS[REPO]
    pr = GitHubPullRequest.from_branches(
        repo=REPO,
        base=args.base_label or ':'.join((repo_info['owner'], repo_info['default_branch'])),
        head=args.head_label,
        github_token=args.github_token,
        verbose=args.verbose,
    )

    git = Git(
        repo_path,
        protocol=args.git_protocol,
        origin_name=args.head_remote,
        upstream_name=args.base_remote,
        verbose=args.verbose,
    )

    if args.clone:
        git.bot_clone_upstream_here(GIT_FORGE, pr.base.owner, pr.base.repo)
    elif not args.verify_current_worktree and not git.bot_working_tree_is_clean():
        raise GitError('manual intervention needed; git current worktree is unclean')

    if not args.verify_head_branch and not args.verify_current_worktree:
        # We need to add the "upstream" / base remote or else verify it exists w/correct URL
        # (unless we are only verifying a head branch's work or the current local worktree)
        git.bot_add_or_verify_remote(args.base_remote, GIT_FORGE, pr.base.owner, pr.base.repo)

    if args.pr or args.verify_head_branch:
        # We need to add the "origin" / head remote or else verify it already exists w/correct URL:
        # - If creating a pull request (--pr), we'll push to this remote later
        # - If verifying a pull request's update (--verify--head-branch), we'll pull from this remote
        git.bot_add_or_verify_remote(args.head_remote, GIT_FORGE, pr.head.owner, pr.head.repo)

    if args.verify_head_branch:
        # Pull from "origin" / head branch so we can verify what was already committed/pushed
        git.bot_fetch_origin()
        git.bot_overwrite_branch(pr.head.branch, f'{args.head_remote}/{pr.head.branch}')
    elif not args.verify_current_worktree:
        # Pull from "upstream" / base branch so that our changes will cleanly merge
        git.bot_fetch_upstream()
        git.bot_overwrite_branch(pr.head.branch, f'{args.base_remote}/{pr.base.branch}')

    starting_point = git.bot_rev_parse('HEAD')

    module_path = git.repo_path / TARGET_FILE
    if not module_path.is_file():
        raise BotError('unable to find yt_dlp.utils.networking module')

    pull_request_body = update_user_agent_range(
        module_path,
        verify=args.verify_head_branch or args.verify_current_worktree,
        verbose=args.verbose,
    )
    commit_message = f'[utils] `random_user_agent`: {pull_request_body}\n\nAuthored by: {pr.head.owner}\n'

    pr.update_body(pull_request_body)
    pr.update_commit_message(commit_message)

    if template := PULL_REQUEST_TEMPLATES.get(pr.base.repo):
        pr.append_to_body(template)

    git.bot_commit(commit_message, {module_path})

    if args.pr:
        if not git.bot_working_tree_is_clean():
            raise GitError('unexpected result: git working tree is unclean')

        git.bot_fetch_origin()
        git.bot_force_push_with_lease_to_origin(pr.head.branch)

        pr.create_or_update()

        raise SuccessMessage(pr.info['html_url'])

    if args.export_patches:
        git.bot_patches(starting_point, args.export_patches)

    if args.export_pr_body:
        args.export_pr_body.parent.mkdir(parents=True, exist_ok=True)
        args.export_pr_body.with_suffix('.md').write_text(pr.body)

    if args.export_commit_message:
        args.export_commit_message.parent.mkdir(parents=True, exist_ok=True)
        args.export_commit_message.with_suffix('.txt').write_text(pr.commit_message)

    print(pull_request_body)


def run(args: argparse.Namespace) -> int:
    try:
        _real_run(args)
    except SuccessMessage as message:
        if os.getenv('GITHUB_ACTIONS'):
            print(f'::notice::{message}')
        else:
            print(message, file=sys.stderr)
        return 0
    except BotError as error:
        if os.getenv('GITHUB_ACTIONS'):
            print(f'::error::{error}')
        else:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        configure_parser(parser)
        sys.exit(run(parser.parse_args()))
    except KeyboardInterrupt:
        print('\nERROR: interrupted by user', file=sys.stderr)
        sys.exit(1)
