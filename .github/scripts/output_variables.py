from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

if not os.getenv('GITHUB_ACTIONS'):
    print('This script is intended to be run in a GitHub Actions environment', file=sys.stderr)
    sys.exit(1)

from bot.knowledge import (
    DEFAULT_HEAD_BRANCHES,
    DEFAULT_HEAD_OWNER,
    SERVICED_REPOS,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'service',
        choices=['actions'],
    )
    service = parser.parse_args().service

    default_head_branch = DEFAULT_HEAD_BRANCHES[service]
    matrix = [v for v in SERVICED_REPOS.values() if service in v['services']]

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

    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f'default_head_branch={default_head_branch}\n')
        f.write(f'default_head_owner={DEFAULT_HEAD_OWNER}\n')
        f.write(f'matrix={json.dumps(matrix)}')


if __name__ == '__main__':
    main()
