"""
Update actions in a GitHub repository's workflows.

It is expected that the environment has `git` available and the `actions` extra installed.
"""

from __future__ import annotations

import argparse
import os
import sys

from bot.command.common import (
    configure_commit_options,
    configure_export_options,
    configure_git_options,
    configure_github_options,
    configure_logging_options,
    configure_remote_target_options,
    configure_update_options,
    configure_update_pr_options,
    get_update_objects,
)
from bot.git import GitError
from bot.github import (
    RelativeBranch,
    get_gha_workflow_run_url,
    make_absolute_branch,
)
from bot.knowledge import (
    DEFAULT_HEAD_BRANCHES,
    DEFAULT_HEAD_OWNER,
    PULL_REQUEST_TEMPLATES,
    SERVICED_REPOS,
)
from bot.utils import (
    BotError,
    SuccessMessage,
    VerificationError,
    safe_format,
    table_a_raza,
)
from bot.workflows import (
    ActionsUpdater,
    ActionsUpdateResultType,
)

try:
    import yaml
except ImportError:
    yaml = None


UPDATE_NAME = 'actions'

DEFAULT_HEAD = RelativeBranch(owner=DEFAULT_HEAD_OWNER, branch=DEFAULT_HEAD_BRANCHES[UPDATE_NAME])

SUPPORTED_REPOS = [k for k, v in SERVICED_REPOS.items() if UPDATE_NAME in v['services']]


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        'repository',
        metavar='REPOSITORY',
        choices=SUPPORTED_REPOS,
        help=f'name of the (upstream) repository. one of: {", ".join(SUPPORTED_REPOS)}',
    )
    # NB: Do not use type=pathlib.Path in arg parser since it would convert empty arg to Path('.')
    parser.add_argument(
        'directory',
        metavar='DIRECTORY',
        nargs=argparse.OPTIONAL,
        help=(
            'local path to the root of the git working tree. '
            'if not provided and --clone is not used, it will default to the CWD ("."). '
            'if not provided and --clone is used, it will default to a temporary directory'
        ),
    )
    # Add common option groups
    configure_remote_target_options(
        parser,
        default_head_label=DEFAULT_HEAD.label,
    )
    configure_update_options(parser, add_exclude_newer=True)
    configure_update_pr_options(parser)
    configure_git_options(parser)
    configure_github_options(parser)
    configure_commit_options(parser, add_commit_type=True)
    configure_export_options(parser)
    configure_logging_options(parser)


def print_table(all_updates: ActionsUpdateResultType):
    for row in table_a_raza(
        ('action', 'old', 'new'),
        [(f'{action.owner}/{action.repo}', old.tag, new.tag) for action, (old, new) in all_updates.items()],
    ):
        print(row)


def _real_run(args: argparse.Namespace):
    if yaml is None:
        raise ImportError(
            'the pyyaml package (yaml library) is required for updates. '
            'install the "update" extra to fulfill the requirements'
        )

    repo_info = SERVICED_REPOS[args.repository]
    _, pr, git, existing_commits = get_update_objects(
        args,
        make_absolute_branch(
            args.base_label or ':'.join((repo_info['owner'], repo_info['default_branch'])),
            args.repository,
        ),
        make_absolute_branch(
            args.head_label or DEFAULT_HEAD.label,
            args.repository,
        ),
    )

    updater = ActionsUpdater.from_git_and_pr(
        git=git,
        pr=pr,
        exclude_newer=args.exclude_newer,
    )

    formatted_prefix = safe_format(args.commit_prefix or repo_info['commit_prefix'], category='ci')
    formatted_addendum = safe_format(args.commit_addendum or repo_info['commit_addendum'], username=pr.head.owner)

    workflows, all_updates = updater.update(
        commit_type=args.commit_type or ('incremental' if args.pr else 'bulk'),
        export_patches=args.export_patches,
        commit_prefix=formatted_prefix,
        commit_addendum=formatted_addendum,
        verify=args.verify,
    )

    if not all_updates:
        raise SuccessMessage('All actions & workflows are up-to-date')
    elif args.verify:
        print_table(all_updates)
        raise VerificationError('Update verification failed')

    pull_request_body, merge_commit_message = updater.parse_results(
        workflows,
        all_updates,
        existing_commits,
        commit_prefix=formatted_prefix,
        commit_addendum=formatted_addendum,
    )
    pr.update_body(pull_request_body)
    pr.update_commit_message(merge_commit_message)

    if template := PULL_REQUEST_TEMPLATES.get(pr.base.repo):
        pr.append_to_body(template)

    if gha_url := get_gha_workflow_run_url():
        pr.append_to_body('---')
        pr.append_to_body(f'*This pull request is the product of [this GitHub Actions workflow run]({gha_url}).*')

    if args.pr:
        if not git.bot_working_tree_is_clean():
            raise GitError('unexpected result: git working tree is unclean')

        git.bot_fetch_origin()
        git.bot_force_push_with_lease_to_origin(pr.head.branch)

        pr.create_or_update()

        raise SuccessMessage(pr.info['html_url'])

    if args.export_pr_body:
        args.export_pr_body.parent.mkdir(parents=True, exist_ok=True)
        args.export_pr_body.with_suffix('.md').write_text(pr.body)

    if args.export_commit_message:
        args.export_commit_message.parent.mkdir(parents=True, exist_ok=True)
        args.export_commit_message.with_suffix('.txt').write_text(pr.commit_message)

    print_table(all_updates)


def run(args: argparse.Namespace) -> int:
    try:
        _real_run(args)
    except SuccessMessage as message:
        if os.getenv('GITHUB_ACTIONS'):
            print(f'::notice::{message}')
        else:
            print(message, file=sys.stderr)
        return 0
    except BotError as error:
        if os.getenv('GITHUB_ACTIONS'):
            print(f'::error::{error}')
        else:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        configure_parser(parser)
        sys.exit(run(parser.parse_args()))
    except KeyboardInterrupt:
        print('\nERROR: interrupted by user', file=sys.stderr)
        sys.exit(1)
