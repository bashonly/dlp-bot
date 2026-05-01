"""
Update actions in a GitHub repository's workflows.

It is expected that the environment has `git` available and the `actions` extra installed.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile

from bot.command.common import (
    configure_commit_options,
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
    BotError,
    SuccessMessage,
    VerificationError,
    safe_format,
    table_a_raza,
)
from bot.workflows import (
    ActionsUpdater,
    ActionsUpdateResult,
)

try:
    import yaml
except ImportError:
    yaml = None


UPDATE_NAME = 'actions'

DEFAULT_HEAD = RelativeBranch(owner=DEFAULT_HEAD_OWNER, branch=DEFAULT_HEAD_BRANCHES[UPDATE_NAME])

SUPPORTED_REPOS = [k for k, v in SERVICED_REPOS.items() if UPDATE_NAME in v['services']]


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        'repository',
        metavar='REPOSITORY',
        choices=SUPPORTED_REPOS,
        help=f'name of the (upstream) repository. one of: {", ".join(SUPPORTED_REPOS)}',
    )
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
    configure_update_options(parser, add_exclude_newer=True)
    configure_git_options(parser)
    configure_github_options(parser)
    configure_commit_options(parser, add_commit_type=True)
    configure_export_options(parser)
    configure_logging_options(parser)


def print_table(all_updates: ActionsUpdateResult):
    for row in table_a_raza(
        ('action', 'old', 'new'),
        [(f'{action.owner}/{action.repo}', old.tag, new.tag) for action, (old, new) in all_updates.items()],
    ):
        print(row)


def _real_run(args: argparse.Namespace):
    if yaml is None:
        raise ImportError(
            'the pyyaml package (yaml library) is required for workflows. '
            'install the "workflows" extra to fulfill the requirements'
        )

    if not args.directory:
        if args.clone:
            repo_path = pathlib.Path(tempfile.mkdtemp())
        else:
            repo_path = pathlib.Path('.')
    else:
        repo_path = pathlib.Path(args.directory)

    repo_info = SERVICED_REPOS[args.repository]
    pr = GitHubPullRequest.from_branches(
        repo=args.repository,
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

    updater = ActionsUpdater.from_git_and_pr(
        git=git,
        pr=pr,
        exclude_newer=args.exclude_newer,
    )

    formatted_prefix = safe_format(args.commit_prefix or repo_info['commit_prefix'], category='ci')
    formatted_addendum = safe_format(args.commit_addendum or repo_info['commit_addendum'], username=pr.head.owner)

    workflows, all_updates = updater.update(
        commit_type=args.commit_type or ('incremental' if args.pr else 'bulk'),
        export_patches=args.export_patches,
        commit_prefix=formatted_prefix,
        commit_addendum=formatted_addendum,
        verify=args.verify_head_branch or args.verify_current_worktree,
    )

    if not all_updates:
        raise SuccessMessage('All actions & workflows are up-to-date')
    elif args.verify_head_branch or args.verify_current_worktree:
        print_table(all_updates)
        raise VerificationError('Update verification failed')

    pull_request_body, merge_commit_message = updater.parse_results(
        workflows,
        all_updates,
        commit_prefix=formatted_prefix,
        commit_addendum=formatted_addendum,
    )
    pr.update_body(pull_request_body)
    pr.update_commit_message(merge_commit_message)

    if template := PULL_REQUEST_TEMPLATES.get(pr.base.repo):
        pr.append_to_body(template)

    if args.pr:
        if not git.bot_working_tree_is_clean():
            raise GitError('unexpected result: git working tree is unclean')

        git.bot_fetch_origin()
        git.bot_force_push_with_lease_to_origin(pr.head.branch)

        pr.create_or_update()

        raise SuccessMessage(pr.info['html_url'])

    if args.export_pr_body:
        args.export_pr_body.parent.mkdir(parents=True, exist_ok=True)
        args.export_pr_body.with_suffix('.md').write_text(pr.body)

    if args.export_commit_message:
        args.export_commit_message.parent.mkdir(parents=True, exist_ok=True)
        args.export_commit_message.with_suffix('.txt').write_text(pr.commit_message)

    print_table(all_updates)


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
