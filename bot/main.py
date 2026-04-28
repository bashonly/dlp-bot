from __future__ import annotations

import argparse
import sys
import types
import typing

import bot.command.pr
import bot.command.pr.create
import bot.command.tools
import bot.command.tools.variables
import bot.command.update
import bot.command.update.actions
import bot.command.update.dependencies
import bot.command.update.ejs
import bot.command.update.protobug
import bot.command.update.user_agent
from bot import __version__


def subcommand_name(module: types.ModuleType) -> str:
    return module.__name__.rpartition('.')[2].replace('_', '-')


def get_doc(module: types.ModuleType) -> tuple[str | None, str | None]:
    doc = module.__doc__
    if not doc:
        return None, None

    lines = doc.splitlines()
    for index, line in enumerate(lines):
        if line:
            return line, '\n'.join(lines[index:])

    return None, None


def _add_intermediate_subcmd(
    module: types.ModuleType,
    parent_parsers_map: dict[str, typing.Any],
    parent_subparsers: argparse._SubParsersAction,
    *,
    aliases: list[str] | None = None,
    deprecated: bool = False,
) -> tuple[dict, argparse._SubParsersAction]:
    """Configures the intermediate subcommand parser and mutates the parsers map.

    Returns its nested map within the parsers map and the intermediate parser's subparsers.
    """
    name = subcommand_name(module)
    help_line, description = get_doc(module)
    aliases = aliases or []
    intermediate_parser = parent_subparsers.add_parser(
        name,
        aliases=aliases,
        help=help_line,
        description=description,
        deprecated=deprecated,
    )
    nested_map: dict[str, typing.Any] = {}
    for key in (name, *aliases):
        parent_parsers_map[key] = nested_map

    return nested_map, intermediate_parser.add_subparsers(
        title=f'{name} subcommands',
        dest=f'_{name}_subcommand',
        required=True,
        metavar='<subcommand>',
    )


def _add_final_subcmd(
    module: types.ModuleType,
    parent_parsers_map: dict[str, types.FunctionType],
    parent_subparsers: argparse._SubParsersAction,
    *,
    aliases: list[str] | None = None,
    deprecated: bool = False,
):
    """Configures the final subcommand parser and mutates the parsers map.

    e.g. for a non-nested final subcmd, pass (m, parsers_map, root_subparsers)
         but for a nested final subcmd, pass (m, parsers_map[parent_subcmd], parent_subparsers)
    """
    name = subcommand_name(module)
    help_line, description = get_doc(module)
    aliases = aliases or []
    final_parser = parent_subparsers.add_parser(
        name,
        aliases=aliases,
        help=help_line,
        description=description,
        deprecated=deprecated,
    )
    module.configure_parser(final_parser)
    for key in (name, *aliases):
        parent_parsers_map[key] = module.run


def _main():
    root_parser = argparse.ArgumentParser(
        prog='dlp-bot',
        description='automated tools for the dlp org',
        # suggest_on_error=True,  # Python>=3.14
    )
    root_parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}',
    )
    root_subparsers = root_parser.add_subparsers(
        title='subcommands',
        dest='_root_subcommand',
        required=True,
        metavar='<subcommand>',
    )
    parsers_map = {}

    nested_map, nested_subparsers = _add_intermediate_subcmd(bot.command.pr, parsers_map, root_subparsers)
    _add_final_subcmd(bot.command.pr.create, nested_map, nested_subparsers)

    nested_map, nested_subparsers = _add_intermediate_subcmd(bot.command.update, parsers_map, root_subparsers)
    _add_final_subcmd(bot.command.update.actions, nested_map, nested_subparsers, aliases=['workflows'])
    _add_final_subcmd(bot.command.update.dependencies, nested_map, nested_subparsers, aliases=['deps'])
    _add_final_subcmd(bot.command.update.ejs, nested_map, nested_subparsers)
    _add_final_subcmd(bot.command.update.protobug, nested_map, nested_subparsers)
    _add_final_subcmd(bot.command.update.user_agent, nested_map, nested_subparsers, aliases=['ua'])

    nested_map, nested_subparsers = _add_intermediate_subcmd(bot.command.tools, parsers_map, root_subparsers)
    _add_final_subcmd(bot.command.tools.variables, nested_map, nested_subparsers)

    args = root_parser.parse_args()
    key = 'root'
    result = parsers_map

    while not callable(result):
        key = getattr(args, f'_{key}_subcommand')
        result = result[key]

    return result(args)


def main():
    try:
        sys.exit(_main())
    except KeyboardInterrupt:
        print('\nERROR: interrupted by user', file=sys.stderr)
        sys.exit(1)
