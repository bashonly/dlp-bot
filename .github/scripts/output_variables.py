from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from bot.knowledge import (
    DEFAULT_HEAD_BRANCHES,
    DEFAULT_HEAD_OWNER,
    SERVICED_REPOS,
)


def main():
    parser = argparse.ArgumentParser(description='this script is intended to be run in a GitHub Actions environment')
    parser.add_argument(
        'service',
        choices=['actions'],
        help='output the variables for this service',
    )
    service = parser.parse_args().service
    in_gha = os.getenv('GITHUB_ACTIONS')
    default_head_branch = DEFAULT_HEAD_BRANCHES[service]
    matrix = [v for v in SERVICED_REPOS.values() if service in v['services']]

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
    sys.exit(main())
