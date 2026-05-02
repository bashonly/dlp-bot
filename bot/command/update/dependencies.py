"""
Update dependencies for a project.

It is expected that the environment has the necessary package manager installed (e.g. `uv`).
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
from bot.deps.common import DependenciesUpdateResult
from bot.deps.dlp_bot import DLPBotDependenciesUpdater
from bot.deps.ejs import EJSDependenciesUpdater, EJSProject
from bot.deps.python import PythonProject
from bot.deps.yt_dlp import YTDLPDependenciesUpdater
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

UPDATE_NAME = 'dependencies'

DEFAULT_HEAD = RelativeBranch(owner=DEFAULT_HEAD_OWNER, branch=DEFAULT_HEAD_BRANCHES[UPDATE_NAME])

SUPPORTED_REPOS = [k for k, v in SERVICED_REPOS.items() if UPDATE_NAME in v['services']]

PROJECTS = {
    'dlp-bot': PythonProject,
    'ejs': EJSProject,
    'yt-dlp': PythonProject,
}

UPDATERS = {
    'dlp-bot': DLPBotDependenciesUpdater,
    'ejs': EJSDependenciesUpdater,
    'yt-dlp': YTDLPDependenciesUpdater,
}

assert all((repo in PROJECTS and repo in UPDATERS) for repo in SUPPORTED_REPOS)

UPGRADE_ONLY_PACKAGES = ('protobug', 'yt-dlp-ejs')


def configure_parser(
    parser: argparse.ArgumentParser,
    *,
    force_repository: str | None = None,
    upgrade_only: str | None = None,
    default_head_label: str | None = None,
):
    if force_repository:
        assert force_repository in SUPPORTED_REPOS, f'{force_repository!r} is not a supported repo'
        # Only reached when another command uses this function w/ a truthy force_repository kwarg.
        # Add a hidden option such that args.repository can only be the forced_repository value
        parser.add_argument(
            '--repository',
            choices=[force_repository],
            default=force_repository,
            help=argparse.SUPPRESS,
        )
    else:
        # Normal operation: add a required first positional argument
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
        default_head_label=default_head_label or DEFAULT_HEAD.label,
        force_repository=force_repository,
    )
    update_group = configure_update_options(parser)
    # Hidden option: only intended for use with `bot update ejs` or `bot update protobug`
    update_group.add_argument(
        '--upgrade-only',
        choices=[upgrade_only] if upgrade_only else UPGRADE_ONLY_PACKAGES,
        default=upgrade_only,
        help=argparse.SUPPRESS,
    )
    configure_git_options(parser)
    configure_github_options(parser)
    configure_commit_options(parser)
    configure_export_options(parser)
    configure_logging_options(parser)


def print_table(all_updates: DependenciesUpdateResult):
    for row in table_a_raza(
        ('package', 'old', 'new'), [(package, old or '', new or '') for package, (old, new) in all_updates.items()]
    ):
        print(row)


def _real_run(args: argparse.Namespace):
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

    starting_point = git.bot_rev_parse('HEAD')

    project = PROJECTS[args.repository](
        repo_path,
        verbose=args.verbose,
    )
    updater = UPDATERS[args.repository](
        project,
        gh=pr.api,
    )

    updated_paths, all_updates = updater.update(
        upgrade_only=args.upgrade_only,
        verify=args.verify_head_branch or args.verify_current_worktree,
    )
    if not all_updates:
        raise SuccessMessage('All dependencies are up-to-date')
    elif args.verify_head_branch or args.verify_current_worktree:
        print_table(all_updates)
        raise VerificationError('Update verification failed')

    pull_request_body, commit_message = updater.parse_results(
        all_updates,
        commit_prefix=safe_format(
            args.commit_prefix or repo_info['commit_prefix'],
            category='build',
        ),
        commit_addendum=safe_format(
            args.commit_addendum or repo_info['commit_addendum'],
            username=pr.head.owner,
        ),
    )
    pr.update_body(pull_request_body)
    pr.update_commit_message(commit_message)

    if template := PULL_REQUEST_TEMPLATES.get(pr.base.repo):
        pr.append_to_body(template)

    git.bot_commit(commit_message, updated_paths)

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
