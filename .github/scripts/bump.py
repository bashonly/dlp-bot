from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tomllib

BASE_PATH = pathlib.Path(__file__).parent.parent.parent

sys.path.insert(0, str(BASE_PATH))


def get_extras_and_groups():
    with (BASE_PATH / 'pyproject.toml').open('rb') as f:
        pyproject = tomllib.load(f)

    return pyproject['project']['optional-dependencies'], pyproject['dependency-groups']


EXTRAS, GROUPS = get_extras_and_groups()


def uv_export(name: str):
    if name in EXTRAS:
        argument = f'--extra={name}'
    elif name in GROUPS:
        argument = f'--group={name}'
    else:
        raise ValueError(f'"{name}" is not an extra or a group')

    output_path = BASE_PATH / f'requirements/{name}.txt'

    return subprocess.check_call(
        [
            'uv',
            'export',
            '--no-python-downloads',
            '--quiet',
            '--no-progress',
            '--color=never',
            '--format=requirements.txt',
            '--frozen',
            '--refresh',
            '--no-emit-project',
            '--no-default-groups',
            argument,
            f'--output-file={output_path.relative_to(BASE_PATH)}',
        ]
    )


def uv_lock_upgrade():
    return subprocess.check_call(['uv', 'lock', '--upgrade'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'subcommand',
        choices=['export', 'lock'],
    )
    if parser.parse_args().subcommand == 'lock':
        return uv_lock_upgrade()

    for name in (*EXTRAS, *GROUPS):
        uv_export(name)

    return 0


if __name__ == '__main__':
    sys.exit(main())
