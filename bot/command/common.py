from __future__ import annotations

import argparse
import os
import pathlib
import typing

from bot.utils import parse_datetime_from_cooldown


def boolean_if_true_negates_others(*dests_to_negate):
    class _BooleanNegateAction(argparse.BooleanOptionalAction):
        def __call__(self, parser, namespace, values, option_string=None):
            super().__call__(parser, namespace, values, option_string=option_string)
            if getattr(namespace, self.dest, None) is True:
                for dest_to_negate in dests_to_negate:
                    setattr(namespace, dest_to_negate, False)

    return _BooleanNegateAction


def configure_remote_target_options(
    parser: argparse.ArgumentParser,
    *,
    default_head_label: str | None = None,
    force_repository: str | None = None,
) -> argparse._ArgumentGroup:
    LABEL_METAVAR = 'OWNER[:REPO]:BRANCH'
    group = parser.add_argument_group('remote target options')

    head_help = f'label for the branch that the pull request should be created from, formatted as {LABEL_METAVAR}'
    head_kwargs: dict[str, typing.Any] = {}
    if default_head_label:
        head_kwargs.update({
            'default': default_head_label,
            'help': f'{head_help}. (default: {default_head_label})',
        })
    else:
        head_kwargs.update({
            'required': True,
            'help': f'{head_help}. (REQUIRED)',
        })
    group.add_argument(
        '-H',
        '--head',
        dest='head_label',
        metavar=LABEL_METAVAR,
        **head_kwargs,
    )

    base_help = (
        'label for the branch that the pull request should be merged into, formatted as {} .'
        'if the REPO segment is not included, the REPO segment will default to {}. '
        'if --base is not used, all segments will default to values that are hardcoded for {}'
    ).format(
        LABEL_METAVAR,
        f'"{force_repository}"' if force_repository else 'the positional REPOSITORY argument',
        f'"{force_repository}"' if force_repository else 'the given repository',
    )
    group.add_argument(
        '-B',
        '--base',
        dest='base_label',
        metavar=LABEL_METAVAR,
        help=base_help,
    )

    return group


def configure_update_options(
    parser: argparse.ArgumentParser,
    *,
    add_exclude_newer: bool = False,
) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('update options')

    group.add_argument(
        '--clone',
        dest='clone',
        default=False,
        action=boolean_if_true_negates_others('verify_current_worktree'),
        help=(
            'whether to create a fresh clone of the repository instead of using an existing local repo '
            '(default: --no-clone) (--clone implies: --no-verify-current-worktree)'
        ),
    )
    group.add_argument(
        '--pr',
        dest='pr',
        default=False,
        action=boolean_if_true_negates_others('verify_head_branch', 'verify_current_worktree'),
        help=(
            'whether to create a pull request targeting the base branch & submit it to the base owner '
            '(default: --no-pr) (--pr implies: --no-verify-head-branch --no-verify-current-worktree)'
        ),
    )
    group.add_argument(
        '--verify-head-branch',
        dest='verify_head_branch',
        default=False,
        action=boolean_if_true_negates_others('pr', 'verify_current_worktree'),
        help=(
            'whether to only verify the previous update that was committed/pushed to the head branch'
            '(default: --no-verify-head-branch) (--verify-head-branch implies: --no-pr --no-verify-current-worktree)'
        ),
    )
    group.add_argument(
        '--verify-current-worktree',
        dest='verify_current_worktree',
        default=False,
        action=boolean_if_true_negates_others('clone', 'pr', 'verify_head_branch'),
        help=(
            'whether to only verify the previous update made to the local current worktree '
            '(default: --no-verify-current-worktree) '
            '(--verify-current-worktree implies: --no-clone --no-pr --no-verify-head-branch)'
        ),
    )

    if add_exclude_newer:
        group.add_argument(
            '--exclude-newer',
            metavar='COOLDOWN',
            help=(
                'exclude versions newer than COOLDOWN, which can be any of: '
                'ISO8601 duration (e.g. "P7D"), '
                'natural language duration (e.g. "7 days"), '
                'ISO8601 timestamp (e.g. "2026-03-28T23:10:22Z"), '
                'or a UNIX timestamp (seconds since the epoch). '
                'an empty argument will set the current timestamp as the COOLDOWN value'
            ),
            type=parse_datetime_from_cooldown,
        )

    return group


def configure_git_options(
    parser: argparse.ArgumentParser,
    *,
    default_head_remote: str = 'origin',
    default_base_remote: str = 'upstream',
) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('git options')

    group.add_argument(
        '--git-protocol',
        choices=['ssh', 'https'],
        help=('protocol to use with git. one of "ssh" (default) or "https"'),
    )
    group.add_argument(
        '--head-remote',
        metavar='REMOTE',
        default=default_head_remote,
        help=f"name of the head repository's git remote in the local repository. (default: {default_head_remote})",
    )
    group.add_argument(
        '--base-remote',
        metavar='REMOTE',
        default=default_base_remote,
        help=f"name of the base repository's git remote in the local repository. (default: {default_base_remote})",
    )

    return group


def configure_github_options(parser: argparse.ArgumentParser) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('github options')
    group.add_argument(
        '--github-token',
        metavar='TOKEN',
        default=os.getenv('GH_TOKEN'),
        help=(
            'GitHub API token (PAT, classic, GHA, etc) used to avoid being rate-limited '
            'and to authenticate for git-pushes and pull request creation. '
            'if this option is not used, the value of the GH_TOKEN environment '
            'variable will be used (if it is set)'
        ),
    )

    return group


def configure_commit_options(
    parser: argparse.ArgumentParser,
    *,
    add_commit_type: bool = False,
) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('commit options')

    group.add_argument(
        '--commit-prefix',
        metavar='PREFIX',
        help=(
            'prefix to add each to each commit subject line and to the pull request title. '
            'defaults are hardcoded per repository'
        ),
    )
    group.add_argument(
        '--commit-addendum',
        metavar='MESSAGE',
        help='an addendum to add to each commit message. defaults are hardcoded per repository',
    )

    if add_commit_type:
        group.add_argument(
            '--commit-type',
            choices=['bulk', 'incremental'],
            help=(
                'one of: '
                '"bulk" (commit changes to the current branch after ALL updates), '
                '"incremental" (commit changes to the current branch after EACH update). '
                'defaults to "bulk" unless the --pr option is used, which defaults to "incremental"'
            ),
        )

    return group


def configure_export_options(parser: argparse.ArgumentParser) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('export options')
    group.add_argument(
        '--export-pr-body',
        metavar='FILEPATH',
        help='if an output filepath is provided, then export the pull request body as a markdown file',
        type=pathlib.Path,
    )
    group.add_argument(
        '--export-commit-message',
        metavar='FILEPATH',
        help='if an output filepath is provided, then export the commit message to a text file',
        type=pathlib.Path,
    )
    group.add_argument(
        '--export-patches',
        metavar='DIRPATH',
        help=(
            'if an output directory path is provided, then export '
            'the commit(s) to patch file(s) in the given output directory'
        ),
        type=pathlib.Path,
    )

    return group


def configure_logging_options(parser: argparse.ArgumentParser) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('logging options')
    group.add_argument(
        '--verbose',
        dest='verbose',
        default=False,
        action=argparse.BooleanOptionalAction,
        help=(
            'whether to print verbose debug output, e.g. for all subprocess calls and network requests '
            '(default: --no-verbose)'
        ),
    )

    return group
