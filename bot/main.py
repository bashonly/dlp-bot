from __future__ import annotations

import argparse
import sys
import types

import bot.command.actions
import bot.command.pr


def get_doc(module: types.ModuleType):
    doc = module.__doc__
    if not doc:
        return None, None

    lines = doc.splitlines()
    for index, line in enumerate(lines):
        if line:
            return line, '\n'.join(lines[index:])

    return None, None


def _main():
    parser = argparse.ArgumentParser(
        prog='dlp-bot',
        description='automated tools for the dlp org',
        # suggest_on_error=True,  # Python>=3.14
    )
    subparsers = parser.add_subparsers(
        title='subcommands',
        dest='action',
        required=True,
        metavar='<subcommand>',
    )

    parsers = {}

    def _add_parser(module: types.ModuleType):
        name = module.__name__.rpartition('.')[2].replace('_', '-')
        help_line, description = get_doc(module)
        parser = subparsers.add_parser(name, help=help_line, description=description)
        module.configure_parser(parser)
        parsers[name] = module.run

    _add_parser(bot.command.actions)
    _add_parser(bot.command.pr)

    args = parser.parse_args()
    parsers[args.action](args)


def main():
    try:
        _main()
    except KeyboardInterrupt:
        print('\nERROR: interrupted by user', file=sys.stderr)
        sys.exit(1)
