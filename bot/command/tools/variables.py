"""
Output variables needed for GitHub Actions workflows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from bot.knowledge import (
    DEFAULT_HEAD_BRANCHES,
    DEFAULT_HEAD_OWNER,
    SERVICED_REPOS,
)


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        'service',
        choices=list(DEFAULT_HEAD_BRANCHES),
        help='the service for which to output variables',
    )


def run(args: argparse.Namespace) -> int:
    in_gha = os.getenv('GITHUB_ACTIONS')
    default_head_branch = DEFAULT_HEAD_BRANCHES[args.service]
    matrix = [v for v in SERVICED_REPOS.values() if args.service in v['services']]

    if in_gha:
        print('::group::Output variables')

    print(
        json.dumps(
            {
                'default_head_branch': default_head_branch,
                'default_head_owner': DEFAULT_HEAD_OWNER,
                'matrix': matrix,
            },
            indent=2,
        ),
    )
    if in_gha:
        print('::endgroup::')
    else:
        return 1

    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f'default_head_branch={default_head_branch}\n')
        f.write(f'default_head_owner={DEFAULT_HEAD_OWNER}\n')
        f.write(f'matrix={json.dumps(matrix)}')

    return 0


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        configure_parser(parser)
        sys.exit(run(parser.parse_args()))
    except KeyboardInterrupt:
        print('\nERROR: interrupted by user', file=sys.stderr)
        sys.exit(1)
