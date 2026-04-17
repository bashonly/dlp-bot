from __future__ import annotations

import typing

SERVICED_REPOS: dict[str, dict[str, typing.Any]] = {
    'yt-dlp': {
        'forge': 'github',
        'owner': 'yt-dlp',
        'repo': 'yt-dlp',
        'default_branch': 'master',
        'commit_prefix': '[ci] ',
        'commit_addendum': 'Authored by: {username}',
        'services': ['actions'],
    },
    'ejs': {
        'forge': 'github',
        'owner': 'yt-dlp',
        'repo': 'ejs',
        'default_branch': 'main',
        'commit_prefix': None,
        'commit_addendum': None,
        'services': ['actions'],
    },
    'protobug': {
        'forge': 'github',
        'owner': 'yt-dlp',
        'repo': 'protobug',
        'default_branch': 'main',
        'commit_prefix': None,
        'commit_addendum': None,
        'services': ['actions'],
    },
    'Pyinstaller-Builds': {
        'forge': 'github',
        'owner': 'yt-dlp',
        'repo': 'Pyinstaller-Builds',
        'default_branch': 'master',
        'commit_prefix': None,
        'commit_addendum': None,
        'services': ['actions'],
    },
    'manylinux-shared': {
        'forge': 'github',
        'owner': 'yt-dlp',
        'repo': 'manylinux-shared',
        'default_branch': 'master',
        'commit_prefix': None,
        'commit_addendum': None,
        'services': [],
    },
    'dlp-bot': {
        'forge': 'github',
        'owner': 'yt-dlp',
        'repo': 'dlp-bot',
        'default_branch': 'main',
        'commit_prefix': None,
        'commit_addendum': None,
        'services': [],  # actions
    },
}

GIT_FORGES: dict[str, dict[str, dict[str, str]]] = {
    'github': {
        'remote_url_templates': {
            'ssh': 'git@github.com:{owner}/{repo}.git',
            'https': 'https://github.com/{owner}/{repo}.git',
        },
    },
    'codeberg': {
        'remote_url_templates': {
            'ssh': 'git@codeberg.org:{owner}/{repo}.git',
            'https': 'https://codeberg.org/{owner}/{repo}.git',
        },
    },
}

ACTIONS: dict[str, dict[str, typing.Any]] = {
    'actions/cache': {
        'owner': 'actions',
        'repo': 'cache',
        'default_branch': 'main',
        'action_slug': 'cache',
    },
    'actions/checkout': {
        'owner': 'actions',
        'repo': 'checkout',
        'default_branch': 'main',
        'action_slug': 'checkout',
    },
    'actions/create-github-app-token': {
        'owner': 'actions',
        'repo': 'create-github-app-token',
        'default_branch': 'main',
        'action_slug': 'create-github-app-token',
    },
    'actions/download-artifact': {
        'owner': 'actions',
        'repo': 'download-artifact',
        'default_branch': 'main',
        'action_slug': 'download-a-build-artifact',
    },
    'actions/setup-python': {
        'owner': 'actions',
        'repo': 'setup-python',
        'default_branch': 'main',
        'action_slug': 'setup-python',
    },
    'actions/upload-artifact': {
        'owner': 'actions',
        'repo': 'upload-artifact',
        'default_branch': 'main',
        'action_slug': 'upload-a-build-artifact',
    },
    'actions/setup-node': {
        'owner': 'actions',
        'repo': 'setup-node',
        'default_branch': 'main',
        'action_slug': 'setup-node-js-environment',
    },
    'astral-sh/ruff-action': {
        'owner': 'astral-sh',
        'repo': 'ruff-action',
        'default_branch': 'main',
        'action_slug': 'ruff-action',
    },
    'dataaxiom/ghcr-cleanup-action': {
        'owner': 'dataaxiom',
        'repo': 'ghcr-cleanup-action',
        'default_branch': 'main',
        'action_slug': 'ghcr-io-cleanup-action',
    },
    'denoland/setup-deno': {
        'owner': 'denoland',
        'repo': 'setup-deno',
        'default_branch': 'main',
        'action_slug': 'setup-deno',
    },
    'docker/login-action': {
        'owner': 'docker',
        'repo': 'login-action',
        'default_branch': 'master',
        'action_slug': 'docker-login',
    },
    'docker/setup-buildx-action': {
        'owner': 'docker',
        'repo': 'setup-buildx-action',
        'default_branch': 'master',
        'action_slug': 'docker-setup-buildx',
    },
    'docker/setup-qemu-action': {
        'owner': 'docker',
        'repo': 'setup-qemu-action',
        'default_branch': 'master',
        'action_slug': 'docker-setup-qemu',
    },
    # Not on marketplace
    'github/codeql-action': {
        'owner': 'github',
        'repo': 'codeql-action',
        'default_branch': 'main',
        'action_slug': None,
    },
    'oven-sh/setup-bun': {
        'owner': 'oven-sh',
        'repo': 'setup-bun',
        'default_branch': 'main',
        'action_slug': 'setup-bun',
    },
    'peter-evans/create-pull-request': {
        'owner': 'peter-evans',
        'repo': 'create-pull-request',
        'default_branch': 'main',
        'action_slug': 'create-pull-request',
    },
    'pnpm/action-setup': {
        'owner': 'pnpm',
        'repo': 'action-setup',
        'default_branch': 'master',
        'action_slug': 'setup-pnpm',
    },
    'pre-commit/action': {
        'owner': 'pre-commit',
        'repo': 'action',
        'default_branch': 'main',
        'action_slug': 'pre-commit',
    },
    'pypa/gh-action-pypi-publish': {
        'owner': 'pypa',
        'repo': 'gh-action-pypi-publish',
        'default_branch': 'unstable/v1',
        'action_slug': 'pypi-publish',
    },
    # Not on marketplace
    'wntrblm/nox': {
        'owner': 'wntrblm',
        'repo': 'nox',
        'default_branch': 'main',
        'action_slug': None,
    },
    # Not on marketplace
    'yt-dlp/rebase-upstream-action': {
        'owner': 'yt-dlp',
        'repo': 'rebase-upstream-action',
        'default_branch': 'master',
        'action_slug': None,
    },
    # Not on marketplace
    'yt-dlp/sanitize-comment': {
        'owner': 'yt-dlp',
        'repo': 'sanitize-comment',
        'default_branch': 'main',
        'action_slug': None,
    },
    'zizmorcore/zizmor-action': {
        'owner': 'zizmorcore',
        'repo': 'zizmor-action',
        'default_branch': 'main',
        'action_slug': 'zizmor-action',
    },
}

PULL_REQUEST_TEMPLATES: dict[str, str] = {
    'yt-dlp': """\
<details open><summary>Template</summary> <!-- OPEN is intentional -->


### Before submitting a *pull request* make sure you have:
- [x] At least skimmed through [contributing guidelines](https://github.com/yt-dlp/yt-dlp/blob/master/CONTRIBUTING.md#developer-instructions) including [yt-dlp coding conventions](https://github.com/yt-dlp/yt-dlp/blob/master/CONTRIBUTING.md#yt-dlp-coding-conventions)
- [x] [Searched](https://github.com/yt-dlp/yt-dlp/search?q=is%3Apr&type=Issues) the bugtracker for similar pull requests

### In order to be accepted and merged into yt-dlp each piece of code must be in public domain or released under [Unlicense](http://unlicense.org/). Check those that apply and remove the others:
- [x] I am the original author of the code in this PR, and I am willing to release it under [Unlicense](http://unlicense.org/)
- [x] I am not the original author of the code in this PR, but it is in the public domain or released under [Unlicense](http://unlicense.org/): This pull request was created by a bot that was written by the maintainers of this project

### What is the purpose of your *pull request*? Check those that apply and remove the others:
- [x] Automated maintenance

</details>
""",
}
