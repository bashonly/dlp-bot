from __future__ import annotations

import argparse
import os
import pathlib
import tempfile
import typing

from bot.git import (
    Commit,
    Git,
    GitError,
)
from bot.github import (
    AbsoluteBranch,
    GitHubPullRequest,
)
from bot.knowledge import GIT_FORGE
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
        '--pr',
        dest='pr',
        default=False,
        action=boolean_if_true_negates_others('use_current_worktree', 'verify'),
        help=(
            'whether to create a pull request targeting the base branch & submit it to the base owner '
            '(default: --no-pr) (--pr implies: --no-use-current-worktree --no-verify)'
        ),
    )
    group.add_argument(
        '--clone',
        dest='clone',
        default=False,
        action=boolean_if_true_negates_others('use_current_worktree'),
        help=(
            'whether to create a fresh clone of the repository instead of using an existing local repo '
            '(default: --no-clone) (--clone implies: --no-use-current-worktree)'
        ),
    )
    group.add_argument(
        '--use-current-worktree',
        dest='use_current_worktree',
        default=False,
        action=boolean_if_true_negates_others('clone', 'pr'),
        help=(
            'whether to update/verify the local current worktree instead of pulling the remote base/head branch '
            '(default: --no-update-current-worktree) (--use-current-worktree implies: --no-clone --no-pr)'
        ),
    )
    group.add_argument(
        '--verify',
        dest='verify',
        default=False,
        action=boolean_if_true_negates_others('pr'),
        help=(
            'whether to only verify the previous update(s) instead of committing update(s) '
            '(default: --no-verify) (--verify implies: --no-pr)'
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


# XXX: should always be used together with bot.common.configure_update_options()
def configure_update_pr_options(parser: argparse.ArgumentParser) -> argparse._ArgumentGroup:
    group = parser.add_argument_group(
        'update pull request options',
        description='these options are only effective if the --pr option is used',
    )
    group.add_argument(
        '--rebase-pr',
        dest='rebase_pr',
        default=False,
        action=boolean_if_true_negates_others('overwrite_pr'),
        help=(
            'whether to rebase an existing pull request branch on the base branch '
            '(default: --no-rebase-pr) (--rebase-pr implies: --no-overwrite-pr)'
        ),
    )
    group.add_argument(
        '--overwrite-pr',
        dest='overwrite_pr',
        default=False,
        action=boolean_if_true_negates_others('rebase_pr'),
        help=(
            'whether to overwrite an existing pull request branch with new-from-scratch updates '
            '(default: --no-overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)'
        ),
    )
    group.add_argument(
        '--pr-command-prefix',
        dest='pr_command_prefix',
        metavar='PREFIX',
        default='@dlp-bot',
        help=(
            'the prefix for commands via pull request comments. the command must be separated '
            'from the prefix by a single space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)'
        ),
    )
    group.add_argument(
        '--pr-command-allowlist',
        dest='pr_command_allowlist',
        metavar='NAME[,NAME...]',
        help=(
            'comma-separated list of usernames and/or team names whose commands via pull '
            'request comments should be acknowledged, e.g. "pukkandan,@yt-dlp/core". '
            'the default behavior is to acknowledge commands from any user'
        ),
    )

    return group


# XXX: should always be used together with bot.common.configure_remote_target_options()
def configure_git_options(parser: argparse.ArgumentParser) -> argparse._ArgumentGroup:
    REMOTE_HELP_TMPL = (
        "name of the {basehead} repository's git remote in the local repository. "
        'the default is "{default}" if the --{basehead} option is not used, '
        'otherwise the default is the OWNER value from the --{basehead} argument'
    )
    group = parser.add_argument_group('git options')
    group.add_argument(
        '--git-protocol',
        choices=['ssh', 'https'],
        help='protocol to use with git. (default: ssh)',
    )
    group.add_argument(
        '--head-remote',
        metavar='REMOTE',
        # XXX: Keep default value in sync with get_update_objects()
        help=REMOTE_HELP_TMPL.format(basehead='head', default='origin'),
    )
    group.add_argument(
        '--base-remote',
        metavar='REMOTE',
        # XXX: Keep default value in sync with get_update_objects()
        help=REMOTE_HELP_TMPL.format(basehead='base', default='upstream'),
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


def get_update_objects(
    args: argparse.Namespace,
    base: AbsoluteBranch,
    head: AbsoluteBranch,
    *,
    base_forge: str = GIT_FORGE,
    head_forge: str = GIT_FORGE,
) -> tuple[pathlib.Path, GitHubPullRequest, Git, list[Commit]]:
    """command.update boilerplate setup function

    `args` is expected to be the result of an argparse.ArgumentParser configured with (at least):
      - bot.common.configure_remote_target_options()
      - bot.common.configure_update_options()
      - bot.common.configure_update_pr_options()
      - bot.common.configure_git_options()
      - bot.common.configure_github_options()
      - bot.common.configure_logging_options()
      - a `directory` attribute (str or None)

    `base` specifies the OWNER:REPO:BRANCH that any updates would be merged into

    `head` specifies the OWNER:REPO:BRANCH that any updates should be pushed to

    `base_forge` specifies the git forge of the base branch; defaults to bot.knowledge.GIT_FORGE

    `head_forge` specifies the git forge of the head branch; defaults to bot.knowledge.GIT_FORGE

    returns a 4-member tuple that consists of:
      1. a pathlib.Path object that points to the local repository's base directory
      2. a bot.github.GitHubPullRequest object initialized for the potential update
      3. a bot.git.Git object initialized with the appropriate local and remote repo info
      4. a list of pre-existing `bot.git.Commit`s on the head branch if a PR is already open
    """
    for attr in (
        'directory',
        # configure_remote_target_options
        'base_label',
        'head_label',
        # configure_update_options
        'clone',
        'pr',
        'use_current_worktree',
        'verify',
        # configure_update_pr_options
        'overwrite_pr',
        'pr_command_allowlist',
        'pr_command_prefix',
        'rebase_pr',
        # configure_git_options
        'git_protocol',
        'base_remote',
        'head_remote',
        # configure_github_options
        'github_token',
        # configure_logging_options
        'verbose',
    ):
        assert hasattr(args, attr), f'args namespace is missing a required attribute: {attr}'

    if not args.directory:
        if args.clone:
            repo_path = pathlib.Path(tempfile.mkdtemp())
        else:
            repo_path = pathlib.Path('.')
    else:
        repo_path = pathlib.Path(args.directory)

    pr = GitHubPullRequest.from_branches(
        repo=base.repo,
        base=base,
        head=head,
        github_token=args.github_token,
        verbose=args.verbose,
    )

    if args.base_remote:
        base_remote = args.base_remote
    elif args.base_label:
        base_remote = base.owner
    else:  # XXX: Keep this in sync with the configure_git_options() default
        base_remote = 'upstream'

    if args.head_remote:
        head_remote = args.head_remote
    elif args.head_label:
        head_remote = head.owner
    else:  # XXX: Keep this in sync with the configure_git_options() default
        head_remote = 'origin'

    git = Git(
        repo_path,
        protocol=args.git_protocol,
        origin_name=head_remote,
        upstream_name=base_remote,
        verbose=args.verbose,
    )

    if args.clone:
        git.bot_clone_upstream_here(base_forge, pr.base.owner, pr.base.repo)

    # To avoid data loss, worktree must be clean unless we are only verifying the current worktree
    if not (args.use_current_worktree and args.verify) and not git.bot_working_tree_is_clean():
        raise GitError('manual intervention needed; git current worktree has uncommitted changes')

    pr_already_exists = args.pr and pr.is_open()
    overwrite_pr = args.overwrite_pr

    # Check for PR command comments posted since the last commit
    if pr_already_exists and not overwrite_pr:
        git.bot_add_or_verify_remote(head_remote, head_forge, pr.head.owner, pr.head.repo)
        git.bot_fetch_origin()
        comments_list = pr.api.paginated_results(
            pr.api.list_issue_comments,
            base.owner,
            base.repo,
            pr.number,
            since=git.bot_get_commit(git.bot_rev_parse(f'refs/remotes/{head_remote}/{pr.head.branch}')).timestamp,
        )
        overwrite_pr_comments = [
            comment for comment in comments_list if f'{args.pr_command_prefix} overwrite' in comment['body']
        ]
        if overwrite_pr_comments:
            if args.pr_command_allowlist:
                commander_ids = set()
                for allowed_name in map(str.strip, args.pr_command_allowlist.split(',')):
                    if allowed_name.startswith('@'):
                        org, _, team_slug = allowed_name.removeprefix('@').partition('/')
                        for member in pr.api.paginated_results(pr.api.list_team_members, org, team_slug):
                            commander_ids.add(member['id'])
                    else:
                        commander_ids.add(pr.api.get_a_user(allowed_name)['id'])
                overwrite_pr = bool(
                    comment for comment in overwrite_pr_comments if comment['user']['id'] in commander_ids
                )
            else:
                overwrite_pr = True

    # Are we updating an existing PR branch?
    if pr_already_exists and not overwrite_pr:
        git.bot_overwrite_branch(pr.head.branch, f'{head_remote}/{pr.head.branch}')

        git.bot_add_or_verify_remote(base_remote, base_forge, pr.base.owner, pr.base.repo)
        git.bot_fetch_upstream()

        if args.rebase_pr:
            git.rebase(f'{base_remote}/{pr.base.branch}')

        return repo_path, pr, git, git.bot_list_new_commits(f'{base_remote}/{pr.base.branch}')

    # Not updating an existing PR branch
    if not args.use_current_worktree:
        if args.pr or args.verify:
            # We need to add the "origin" / head remote or else verify it already exists w/correct URL:
            # - If creating a pull request (--pr), we'll push to this remote later
            # - If verifying a PR's update (--verify --no-use-current-worktree), we pull from this remote
            git.bot_add_or_verify_remote(head_remote, head_forge, pr.head.owner, pr.head.repo)

        if args.verify:
            # Pull from "origin" / head branch so we can verify what was already committed/pushed
            git.bot_fetch_origin()
            git.bot_overwrite_branch(pr.head.branch, f'{head_remote}/{pr.head.branch}')
        else:
            # We need to add the "upstream" / base remote or else verify it exists w/correct URL
            # (unless we are only verifying a head branch's work or using the current local worktree)
            git.bot_add_or_verify_remote(base_remote, base_forge, pr.base.owner, pr.base.repo)
            # Pull from "upstream" / base branch so that our changes will cleanly merge
            git.bot_fetch_upstream()
            git.bot_overwrite_branch(pr.head.branch, f'{base_remote}/{pr.base.branch}')

        existing_commits = []

    elif not args.verify:
        # Get pre-existing commits since we are using the local current worktree
        git.bot_add_or_verify_remote(base_remote, base_forge, pr.base.owner, pr.base.repo)
        git.bot_fetch_upstream()
        existing_commits = git.bot_list_new_commits(f'{base_remote}/{pr.base.branch}')

    return repo_path, pr, git, existing_commits
