from __future__ import annotations

import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

from bot.knowledge import GIT_FORGES
from bot.utils import BotError, remove_around


class GitError(BotError):
    pass


class Git:
    _SUPPORTED_PROTOCOLS = ('ssh', 'https')

    def __init__(
        self,
        /,
        repo_path: pathlib.Path,
        *,
        protocol: str | None = None,
        origin_name: str | None = None,
        upstream_name: str | None = None,
        verbose: bool = False,
    ):
        self.repo_path = pathlib.Path(repo_path).expanduser().resolve()
        self.repo_path.mkdir(parents=True, exist_ok=True)

        exe_location = shutil.which('git')
        if not exe_location:
            raise GitError('git executable could not be found')
        if not os.access(exe_location, os.F_OK | os.X_OK) or os.path.isdir(exe_location):
            raise GitError(f'unable to execute {exe_location!r}')

        self._exe: str = exe_location
        self._base_args: list[str] = ['-C', str(self.repo_path)]
        self.verbose = verbose

        if not self.bot_version().startswith('git '):
            raise GitError(f'invalid output from {self._exe}')

        if protocol:
            if protocol not in self._SUPPORTED_PROTOCOLS:
                raise ValueError(f'{protocol} is not a supported git protocol')
            self.protocol = protocol
        else:
            self.protocol = self._determine_protocol()

        self._origin_name = origin_name
        self._upstream_name = upstream_name

    def _determine_protocol(self, /) -> str:
        def any_remote_startswith(prefix: str) -> bool:
            return any(
                remote.rpartition(' ')[2].startswith(prefix)
                for remote in self.bot_config_re_search(r'remote\.[^.]+\.url')
            )

        if any_remote_startswith('git@'):
            return 'ssh'

        if any_remote_startswith('https://'):
            return 'https'

        return 'ssh'

    def _git(self, /, *args: str) -> list[str]:
        null = False

        for arg in args:
            if arg == '--null':
                null = True
                break
            if arg == '--':
                break

        cmd = [self._exe, *self._base_args, *args]
        if self.verbose:
            print(f'[git] {shlex.join(cmd)}', file=sys.stderr)

        try:
            output = subprocess.check_output(cmd, text=True)
        except subprocess.CalledProcessError as error:
            raise GitError(error)

        if null:
            return output.split('\x00')
        return output.splitlines()

    # Basic low-level git operations

    def add(self, /, *args: str) -> list[str]:
        return self._git('add', *args)

    def apply(self, /, *args: str) -> list[str]:
        return self._git('apply', *args)

    def branch(self, /, *args: str) -> list[str]:
        return self._git('branch', *args)

    def checkout(self, /, *args: str) -> list[str]:
        return self._git('checkout', *args)

    def cherry_pick(self, /, *args: str) -> list[str]:
        return self._git('cherry-pick', *args)

    def clone(self, /, *args: str) -> list[str]:
        return self._git('clone', *args)

    def commit(self, /, *args: str) -> list[str]:
        return self._git('commit', *args)

    def config(self, /, *args: str) -> list[str]:
        return self._git('config', *args)

    def diff(self, /, *args: str) -> list[str]:
        return self._git('diff', *args)

    def fetch(self, /, *args: str) -> list[str]:
        return self._git('fetch', *args)

    def format_patch(self, /, *args: str) -> list[str]:
        return self._git('format-patch', *args)

    def init(self, /, *args: str) -> list[str]:
        return self._git('init', *args)

    def log(self, /, *args: str) -> list[str]:
        return self._git('log', *args)

    def merge(self, /, *args: str) -> list[str]:
        return self._git('merge', *args)

    def mv(self, /, *args: str) -> list[str]:
        return self._git('mv', *args)

    def pull(self, /, *args: str) -> list[str]:
        return self._git('pull', *args)

    def push(self, /, *args: str) -> list[str]:
        return self._git('push', *args)

    def rebase(self, /, *args: str) -> list[str]:
        return self._git('rebase', *args)

    def remote(self, /, *args: str) -> list[str]:
        return self._git('remote', *args)

    def reset(self, /, *args: str) -> list[str]:
        return self._git('reset', *args)

    def restore(self, /, *args: str) -> list[str]:
        return self._git('restore', *args)

    def rev_parse(self, /, *args: str) -> list[str]:
        return self._git('rev-parse', *args)

    def revert(self, /, *args: str) -> list[str]:
        return self._git('revert', *args)

    def rm(self, /, *args: str) -> list[str]:
        return self._git('rm', *args)

    def version(self, /, *args) -> list[str]:
        return self._git('version', *args)

    # Higher-level methods (`bot_`-prefixed)

    def bot_version(self, /) -> str:
        return self.version()[0]

    def bot_rev_parse(self, /, revision: str) -> str:
        if result := self.rev_parse(revision):
            return result[0]
        raise GitError(f'git command failed to return a value: git rev-parse -- {revision}')

    def bot_current_branch(self, /) -> str:
        if result := self.branch('--show-current'):
            return result[0]
        raise GitError('git command failed to return a value: git branch --show-current')

    def bot_working_tree_is_clean(self, /) -> bool:
        return not self.diff('--name-only') and not self.diff('--name-only', '--cached')

    def bot_overwrite_branch(self, /, target_branch: str, start_point: str) -> None:
        if self.bot_current_branch() == target_branch:
            self.checkout(self.bot_rev_parse('HEAD'))
        self.checkout('-B', target_branch, start_point)

    def bot_config_re_search(self, /, pattern: str) -> list[str]:
        try:
            return self.config('--null', '--get-regexp', pattern)
        except GitError:
            return []

    def bot_get_remote_by_url(self, /, remote_url: str) -> str | None:
        for remote in self.bot_config_re_search(r'remote\.[^.]+\.url'):
            setting, _, url = remote.partition(' ')
            if url.strip() == remote_url:
                return remove_around(setting.strip(), 'remote.', '.url')

        return None

    def bot_check_if_remote_exists(self, /, remote_name: str) -> bool:
        return bool(self.bot_config_re_search(re.escape(f'remote.{remote_name}.url')))

    def bot_make_remote_url(self, /, forge: str, owner: str, repo: str) -> str:
        forge = forge.lower()
        if forge not in GIT_FORGES:
            raise ValueError(f'unsupported git forge: {forge}')

        templates = GIT_FORGES[forge]['remote_url_templates']
        if self.protocol not in templates:
            raise ValueError(f'unsupported protcol for {forge} forge: {self.protocol}')

        return templates[self.protocol].format(owner=owner, repo=repo)

    def bot_get_remote_url(self, /, remote_name: str, *, push: bool = False) -> str:
        git_args = ['get-url', '--push' if push else '--no-push', '--', remote_name]
        try:
            return self.remote(*git_args)[0]
        except (GitError, IndexError):
            raise GitError(f'unable to get remote URL for "{remote_name}"')

    def bot_add_or_verify_remote(
        self,
        /,
        remote_name: str,
        forge: str,
        owner: str,
        repo: str,
        *,
        push: bool = False,
    ) -> None:
        remote_url = self.bot_make_remote_url(forge, owner, repo)
        if not self.bot_check_if_remote_exists(remote_name):
            self.remote('add', '--', remote_name, remote_url)
            return

        actual_remote_url = self.bot_get_remote_url(remote_name, push=push)
        if actual_remote_url in (remote_url, remote_url.removesuffix('.git')):
            return

        raise GitError(
            f'"{remote_name}" ({"push" if push else "fetch"}): expected {remote_url!r}, got {actual_remote_url!r}'
        )

    def bot_clone_upstream_here(self, /, forge: str, owner: str, repo: str) -> None:
        if not self._upstream_name:
            raise ValueError('an upstream remote was not configured')

        upstream_url = self.bot_make_remote_url(forge, owner, repo)
        self.clone('--origin', self._upstream_name, upstream_url, str(self.repo_path))

    def bot_fetch_upstream(self, /) -> list[str]:
        if not self._upstream_name:
            raise ValueError('an upstream remote was not configured')

        return self.fetch('--no-tags', '--', self._upstream_name)

    def bot_fetch_origin(self, /) -> list[str]:
        if not self._origin_name:
            raise ValueError('an origin remote was not configured')

        return self.fetch('--no-tags', '--', self._origin_name)

    def bot_force_push_with_lease_to_origin(self, /, refspec: str) -> list[str]:
        if not self._origin_name:
            raise ValueError('an origin remote was not configured')

        return self.push('--force-with-lease', '--', self._origin_name, refspec)

    def bot_commit(
        self,
        /,
        commit_message: str,
        updated_paths: set[pathlib.Path],
    ) -> list[str]:
        self.add('--', *map(str, updated_paths))
        return self.commit('-m', commit_message)

    def bot_patches(
        self,
        /,
        since_or_range: str,
        output_dir: str | pathlib.Path | None = None,
    ) -> list[str]:
        git_args = ['--keep-subject']
        if output_dir:
            git_args.extend([
                '--output-directory',
                str(pathlib.Path(output_dir).resolve()),
            ])

        return self.format_patch(*git_args, since_or_range)

    def bot_get_commit_subject(self, /, revision: str) -> str:
        git_args = ['--format=%s', f'{revision}^-']
        if result := self.log(*git_args):
            return result[0]
        raise GitError(f'git command failed to return a value: git log {shlex.join(git_args)}')
