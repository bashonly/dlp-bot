"""
Update the meriyah version used in ejs.

It is expected that the environment has `pnpm`, `npm`, `bun` and `deno` installed.
"""

from __future__ import annotations

import argparse
import sys

import bot.command.update.dependencies
from bot.github import RelativeBranch
from bot.knowledge import (
    DEFAULT_HEAD_BRANCHES,
    DEFAULT_HEAD_OWNER,
)

UPDATE_NAME = 'meriyah'

DEFAULT_HEAD = RelativeBranch(owner=DEFAULT_HEAD_OWNER, branch=DEFAULT_HEAD_BRANCHES[UPDATE_NAME])


def configure_parser(parser: argparse.ArgumentParser):
    bot.command.update.dependencies.configure_parser(
        parser,
        force_repository='yt-dlp',
        upgrade_only='meriyah',
        default_head_label=DEFAULT_HEAD.label,
    )


def run(args: argparse.Namespace) -> int:
    return bot.command.update.dependencies.run(args)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        configure_parser(parser)
        sys.exit(run(parser.parse_args()))
    except KeyboardInterrupt:
        print('\nERROR: interrupted by user', file=sys.stderr)
        sys.exit(1)
