from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

if not os.getenv('GITHUB_ACTIONS'):
    print('This script is intended to be run in a GitHub Actions environment', file=sys.stderr)
    sys.exit(1)

from bot.knowledge import SERVICED_REPOS

matrix = [v for v in SERVICED_REPOS.values() if 'actions' in v['services']]

for m in matrix:
    if m['repo'] == 'protobug':
        m['test'] = True
    else:
        m['test'] = False

print(json.dumps(matrix, indent=2))
with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
    f.write(f'matrix={json.dumps(matrix)}')
