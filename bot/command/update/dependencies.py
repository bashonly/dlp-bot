#!/usr/bin/env python
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

from bot.deps.python import (
    PythonDependenciesUpdater,
    PythonProject,
)
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
    # 'ejs': 'NodeProject',
    'yt-dlp': PythonProject,
}

UPDATERS = {
    'dlp-bot': PythonDependenciesUpdater,
    # 'ejs': NodeDependenciesUpdater,
    'yt-dlp': YTDLPDependenciesUpdater,
}

assert all((repo in PROJECTS and repo in UPDATERS) for repo in SUPPORTED_REPOS)


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
    parser.add_argument(
        '-B',
        '--base',
        dest='base_label',
        metavar='OWNER[:REPO]:BRANCH',
        help=(
            'label for the branch that the pull request should be merged into, '
            'formatted as {owner}[:{repo}]{branch}. if "repo" is not provided, '
            'it will default to the value of the positional REPOSITORY argument. '
            'if --base is not used, it will default to a value that is '
            'hardcoded for the given repository'
        ),
    )
    parser.add_argument(
        '-H',
        '--head',
        dest='head_label',
        default=DEFAULT_HEAD.label,
        metavar='OWNER[:REPO]:BRANCH',
        help=(
            'label for the branch that the pull request should be created from, '
            'formatted as {owner}[:{repo}]{branch}. if not provided, it will default to '
            f'{DEFAULT_HEAD}'
        ),
    )
    parser.add_argument(
        '--clone',
        dest='clone',
        action='store_true',
        help='create a fresh clone of the repository instead of using an existing local repo',
    )
    parser.add_argument(
        '--no-clone',
        dest='clone',
        action='store_false',
        default=False,
        help='do not clone the repository; operate on an existing local repo (default)',
    )
    parser.add_argument(
        '--verify',
        dest='verify',
        action='store_true',
        help='only verify the previous update; do not generate a pull request body or create a PR',
    )
    parser.add_argument(
        '--no-verify',
        dest='verify',
        action='store_false',
        default=False,
        help='update normally instead of verifying the previous update (default)',
    )
    parser.add_argument(
        '--pr',
        dest='pr',
        action='store_true',
        help='create a pull request targeting the base branch and submit it to the base owner',
    )
    parser.add_argument(
        '--no-pr',
        dest='pr',
        action='store_false',
        default=False,
        help='do not create or submit a pull request (default)',
    )
    parser.add_argument(
        '--head-remote',
        metavar='REMOTE',
        default='origin',
        help=('name of the head repository\'s git remote in the local repository clone. (default: "origin")'),
    )
    parser.add_argument(
        '--base-remote',
        metavar='REMOTE',
        default='upstream',
        help=('name of the base repository\'s git remote in the local repository clone. (default: "upstream")'),
    )
    parser.add_argument(
        '--github-token',
        metavar='TOKEN',
        default=os.getenv('GH_TOKEN'),
        help=(
            'GitHub token (PAT, classic, GHA, etc) used for API authentication. '
            'if this option is not used, the value of the GH_TOKEN environment '
            'variable will be used (if it is set)'
        ),
    )
    parser.add_argument(
        '--git-protocol',
        choices=['ssh', 'https'],
        help=('protocol to use with git. one of "ssh" (default) or "https"'),
    )
    parser.add_argument(
        '--export-pr',
        metavar='DIRPATH',
        help=(
            'if an output directory path is provided, then export '
            'the pull request body and commit message to files in the given output directory'
        ),
        type=pathlib.Path,
    )
    parser.add_argument(
        '--export-patches',
        metavar='DIRPATH',
        help=(
            'if an output directory path is provided, then export '
            'the commit(s) to patch file(s) in the given output directory'
        ),
        type=pathlib.Path,
    )
    parser.add_argument(
        '--commit-prefix',
        metavar='PREFIX',
        help=(
            'prefix to add each to each commit subject line and to the pull request title. '
            'defaults are hardcoded per repository'
        ),
    )
    parser.add_argument(
        '--commit-addendum',
        metavar='MESSAGE',
        help='an addendum to add to each commit message. defaults are hardcoded per repository',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='print verbose debug output (for all network requests)',
    )


def print_table(all_updates):  # TODO: typing
    for row in table_a_raza(
        ('package', 'old', 'new'), [(package, old or '', new or '') for package, (old, new) in all_updates.items()]
    ):
        print(row)


def _real_run(args: argparse.Namespace):
    if not args.directory:
        if args.clone:
            repo_dir = pathlib.Path(tempfile.mkdtemp())
        else:
            repo_dir = pathlib.Path('.').resolve()
    else:
        repo_dir = pathlib.Path(args.directory).resolve()

    repo_info = SERVICED_REPOS[args.repository]
    pr = GitHubPullRequest.from_branches(
        repo=args.repository,
        base=args.base_label or ':'.join((repo_info['owner'], repo_info['default_branch'])),
        head=args.head_label,
        github_token=args.github_token,
        verbose=args.verbose,
    )

    git = Git(
        str(repo_dir),
        protocol=args.git_protocol,
        origin_name=args.head_remote,
        upstream_name=args.base_remote,
        verbose=args.verbose,
    )

    if args.clone:
        git.bot_clone_upstream_here(GIT_FORGE, pr.base.owner, pr.base.repo)
    elif not git.bot_working_tree_is_clean():
        raise GitError('manual intervention needed; git working tree is unclean')

    # upstream
    git.bot_add_or_verify_remote(args.base_remote, GIT_FORGE, pr.base.owner, pr.base.repo)
    if args.pr and not args.verify:
        # we only interact with the origin remote if a pull request is being created
        git.bot_add_or_verify_remote(args.head_remote, GIT_FORGE, pr.head.owner, pr.head.repo)

    git.bot_fetch_upstream()
    git.bot_overwrite_branch(pr.head.branch, f'{args.base_remote}/{pr.base.branch}')
    starting_point = git.bot_rev_parse('HEAD')

    project = PROJECTS[args.repository](str(repo_dir), verbose=args.verbose)
    updater = UPDATERS[args.repository](project, pr.api)

    updated_paths, all_updates = updater.update(verify=args.verify)
    if not all_updates:
        raise SuccessMessage('All dependencies are up-to-date')
    elif args.verify:
        print_table(all_updates)
        raise VerificationError('Update verification failed')

    pull_request_body, commit_message = updater.parse_results(
        all_updates,
        commit_prefix=args.commit_prefix or repo_info['commit_prefix'],
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

    if args.export_pr:
        args.export_pr.mkdir(parents=True, exist_ok=True)
        (args.export_pr / 'pull-request.dependencies.md').write_text(pr.body)
        (args.export_pr / 'commit-message.dependencies.txt').write_text(pr.commit_message)
    else:
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
