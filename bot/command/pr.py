#!/usr/bin/env python
"""
Create a pull request on an upstream GitHub repository.

All changes are expected to be already committed and pushed to the remote head branch.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

from bot.github import GitHubPullRequest
from bot.knowledge import (
    PULL_REQUEST_TEMPLATES,
    SERVICED_REPOS,
)
from bot.utils import (
    BotError,
    SuccessMessage,
)

FILE_PREFIX = 'file:'


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        'repository',
        metavar='REPOSITORY',
        choices=list(SERVICED_REPOS),
        help=f'name of the (upstream) repository. one of: {", ".join(SERVICED_REPOS)}',
    )
    parser.add_argument(
        '-H', '--head',
        dest='head_label',
        metavar='OWNER[:REPO]:BRANCH',
        required=True,
        help=(
            'label for the branch that the pull request should be created from, '
            'formatted as {owner}[:{repo}]{branch} (REQUIRED)'
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
        '--title',
        metavar='TITLE',
        help=(
            'the title of the pull request. prefix the argument with '
            f'"{FILE_PREFIX}" to load the title from a file instead'
        ),
    )
    parser.add_argument(
        '--body',
        metavar='BODY',
        help=(
            'the body/description of the pull request. prefix the argument with '
            f'"{FILE_PREFIX}" to load the body from a file instead'
        ),
    )
    parser.add_argument(
        '--template',
        metavar='TEMPLATE',
        help=(
            'a pull request template to append to the PR body. prefix the argument with '
            f'"{FILE_PREFIX}" to load the template from a file instead. if not provided, '
            'will default to a hardcoded value for the given repository (if one exists)'
        ),
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='print verbose debug output (for all network requests)',
    )


def _real_run(args: argparse.Namespace):
    repo_info = SERVICED_REPOS[args.repository]

    pr = GitHubPullRequest.from_branches(
        repo=args.repository,
        base=args.base_label or ':'.join((repo_info['owner'], repo_info['default_branch'])),
        head=args.head_label,
        github_token=args.github_token,
        verbose=args.verbose,
    )

    if title := args.title:
        if title.startswith(FILE_PREFIX):
            title = pathlib.Path(title.removeprefix(FILE_PREFIX)).read_text()
        pr.update_title(title)

    if body := args.body:
        if body.startswith(FILE_PREFIX):
            body = pathlib.Path(body.removeprefix(FILE_PREFIX)).read_text()
        pr.update_body(body)

    if template := (args.template or PULL_REQUEST_TEMPLATES.get(pr.base.repo)):
        if template.startswith(FILE_PREFIX):
            template = pathlib.Path(template.removeprefix(FILE_PREFIX)).read_text()
        pr.append_to_body(template)

    if pr.is_created():
        print(f'PR #{pr.number} already exists, updating its info', file=sys.stderr)
        pr.update()
    else:
        pr.create()

    raise SuccessMessage(pr.info['url'])


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
