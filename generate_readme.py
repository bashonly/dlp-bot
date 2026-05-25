from __future__ import annotations

import collections.abc
import pathlib
import shlex
import subprocess
import sys

BASE_PATH = pathlib.Path(__file__).parent
README = BASE_PATH / 'README.md'

HEADER = '# dlp-bot\nautomated tools for the dlp org\n\n## Usage\n\n'

SUBCOMMAND_MAP: dict[str, list[str]] = {
    'pr': [
        'create',
    ],
    'tools': [
        'variables',
    ],
    'update': [
        'actions',
        'astring',
        'dependencies',
        'ejs',
        'meriyah',
        'protobug',
        'user-agent',
    ],
}


def generate_help_output(*args: str) -> collections.abc.Generator[str]:
    cmd = [sys.executable, '-m', 'bot', *args, '--help']
    output = subprocess.run(
        cmd,
        cwd=str(BASE_PATH),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout

    yield f'$ {shlex.join(["python", *cmd[1:]])}\n\n'
    yield from output.splitlines(True)


def yield_readme(header: str, subcommand_map: dict[str, list[str]]) -> collections.abc.Generator[str]:
    yield header

    yield '```\n'
    yield from generate_help_output()
    yield '```\n\n'

    for subcommand, sub_subcommands in subcommand_map.items():
        yield f'### {subcommand}\n\n'
        yield '```\n'
        yield from generate_help_output(subcommand)
        yield '```\n\n'

        for sub_subcommand in sub_subcommands:
            yield f'### {subcommand} {sub_subcommand}\n\n'
            yield '```\n'
            yield from generate_help_output(subcommand, sub_subcommand)
            yield '```\n\n'


def main():
    with README.open(mode='w') as f:
        f.writelines(yield_readme(HEADER, SUBCOMMAND_MAP))


if __name__ == '__main__':
    main()
