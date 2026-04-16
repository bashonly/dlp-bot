#!/usr/bin/env python
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

from bot.git import Git, GitError
from bot.github import GitHubPullRequest
from bot.knowledge import (
    PULL_REQUEST_TEMPLATES,
    SERVICED_REPOS,
)
from bot.utils import (
    BotError,
    SuccessMessage,
    parse_datetime_from_cooldown,
    safe_format,
    table_a_raza,
)
from bot.workflows import ActionsUpdater

try:
    import yaml
except ImportError:
    yaml = None


GIT_FORGE = 'github'

DEFAULT_HEAD_LABEL = 'dlp-bot:bot/update-actions'


# Example usage:
# $ bot actions yt-dlp
# $ bot actions --pr yt-dlp .
# $ bot actions Pyinstaller-Builds /path/to/Pyinstaller-Builds
# $ bot actions --clone --pr ejs
# $ bot actions --pr --base yt-dlp:main --head dlp-bot:feature protobug .
# $ bot actions --clone --pr -B yt-dlp:master -H dlp-bot:bot/update-actions /path/to/cloning/dir
def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        'repository',
        metavar='REPOSITORY',
        choices=list(SERVICED_REPOS),
        help=f'name of the (upstream) repository. one of: {", ".join(SERVICED_REPOS)}',
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
        '-B', '--base',
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
        '-H', '--head',
        dest='head_label',
        default=DEFAULT_HEAD_LABEL,
        metavar='OWNER[:REPO]:BRANCH',
        help=(
            'label for the branch that the pull request should be created from, '
            'formatted as {owner}[:{repo}]{branch}. if not provided, it will default to '
            f'{DEFAULT_HEAD_LABEL}'
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
        help=(
            'name of the head repository\'s git remote in the local repository clone. '
            '(default: "origin")'
        ),
    )
    parser.add_argument(
        '--base-remote',
        metavar='REMOTE',
        default='upstream',
        help=(
            'name of the base repository\'s git remote in the local repository clone. '
            '(default: "upstream")'
        ),
    )
    parser.add_argument(
        '--exclude-newer',
        metavar='COOLDOWN',
        default=os.getenv('DLPBOT_ACTIONS_COOLDOWN'),
        help=(
            'exclude versions newer than COOLDOWN, which can be any of: '
            'ISO8601 duration (e.g. "P7D"), '
            'natural language duration (e.g. "7 days"), '
            'ISO8601 timestamp (e.g. "2026-03-28T23:10:22Z"), '
            'or a UNIX timestamp (seconds since the epoch). '
            'if not provided, the value of the DLPBOT_ACTIONS_COOLDOWN environment variable '
            'will be used if set, or else the default is no cooldown'
        ),
        type=parse_datetime_from_cooldown,
    )
    parser.add_argument(
        '--github-token',
        metavar='TOKEN',
        default=os.getenv('GH_TOKEN'),
        help=(
            'GitHub API token (PAT, classic, GHA, etc) used to avoid being rate-limited '
            'and to authenticate for git-pushes and pull request creation. '
            'if this option is not used, the value of the GH_TOKEN environment '
            'variable will be used (if it is set)'
        ),
    )
    parser.add_argument(
        '--git-protocol',
        choices=['ssh', 'https'],
        default=os.getenv('DLPBOT_GIT_PROTOCOL'),
        help=(
            'protocol to use with git. if not provided, the value of the DLPBOT_GIT_PROTOCOL '
            'environment variable will be used if set, or else the default is "ssh"'
        ),
    )
    parser.add_argument(
        '--commit-type',
        choices=['bulk', 'incremental'],
        help=(
            'one of: '
            '"bulk" (commit changes to the current branch after ALL actions are updated), '
            '"incremental" (commit changes to the current branch after EACH action is updated). '
            'defaults to "bulk" unless the --pr option is used, which defaults to "incremental"'
        ),
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
        help='print verbose debug output (for all git operations and network requests)',
    )


def _real_run(args: argparse.Namespace):
    if yaml is None:
        raise ImportError(
            'the pyyaml package (yaml library) is required for workflows. '
            'install the "workflows" extra to fulfill the requirements')

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
    # upstream
    git.bot_add_or_verify_remote(args.base_remote, GIT_FORGE, pr.base.owner, pr.base.repo)
    if args.pr:
        # we only interact with the origin remote if a pull request is being created
        git.bot_add_or_verify_remote(args.head_remote, GIT_FORGE, pr.head.owner, pr.head.repo)

    if args.clone:
        git.bot_clone_upstream_here(GIT_FORGE, pr.base.owner, pr.base.repo)
    elif not git.bot_working_tree_is_clean():
        raise GitError('manual intervention needed; git working tree is unclean')

    git.bot_fetch_upstream()
    git.bot_overwrite_branch(pr.head.branch, f'{args.base_remote}/{pr.base.branch}')

    updater = ActionsUpdater.from_git_and_pr(
        git=git,
        pr=pr,
        exclude_newer=args.exclude_newer,
    )

    formatted_addendum = safe_format(
        args.commit_addendum or repo_info['commit_addendum'],
        username=pr.head.owner)

    workflows, all_updates = updater.update(
        commit_type=args.commit_type or ('incremental' if args.pr else 'bulk'),
        export_patches=args.export_patches,
        commit_prefix=args.commit_prefix or repo_info['commit_prefix'],
        commit_addendum=formatted_addendum,
    )

    if not all_updates:
        raise SuccessMessage('All actions & workflows are up-to-date')

    pull_request_body, merge_commit_message = updater.parse_results(
        workflows,
        all_updates,
        commit_prefix=args.commit_prefix or repo_info['commit_prefix'],
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

        pull_request_url = pr.create()['url']
        raise SuccessMessage(pull_request_url)

    if args.export_pr:
        args.export_pr.mkdir(parents=True, exist_ok=True)
        (args.export_pr / 'pull-request.bot.md').write_text(pr.body)
        (args.export_pr / 'commit-message.bot.txt').write_text(pr.commit_message)
    else:
        for row in table_a_raza(('action', 'old', 'new'), [
            (f'{action.owner}/{action.repo}', old.tag, new.tag)
            for action, (old, new) in all_updates.items()
        ]):
            print(row)


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
