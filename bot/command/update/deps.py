#!/usr/bin/env python
"""
Update dependencies for a project.

It is expected that the environment has the necessary package manager installed (e.g. `uv`).
"""

from __future__ import annotations

import argparse
import os
import sys

from bot.knowledge import SERVICED_REPOS
from bot.utils import BotError, SuccessMessage


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        'repository',
        metavar='REPOSITORY',
        choices=list(SERVICED_REPOS),
        help=f'name of the (upstream) repository. one of: {", ".join(SERVICED_REPOS)}',
    )
    parser.add_argument(
        '-H',
        '--head',
        dest='head_label',
        metavar='OWNER[:REPO]:BRANCH',
        required=True,
        help=(
            'label for the branch that the pull request should be created from, '
            'formatted as {owner}[:{repo}]{branch} (REQUIRED)'
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
        '--verbose',
        action='store_true',
        help='print verbose debug output (for all network requests)',
    )


def _real_run(args: argparse.Namespace):
    raise SuccessMessage('great success')


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
