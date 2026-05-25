# dlp-bot
automated tools for the dlp org

## Usage

$ python -m bot --help

usage: bot [-h] [--version] <subcommand> ...

automated tools for the dlp org

options:
  -h, --help    show this help message and exit
  --version     show program's version number and exit

subcommands:
  <subcommand>
    pr          Manage GitHub pull requests.
    update      Update actions, dependencies, etc.
    tools       Internal bot tools.
### pr

```
$ python -m bot pr --help

usage: bot pr [-h] <subcommand> ...

Manage GitHub pull requests.

options:
  -h, --help    show this help message and exit

pr subcommands:
  <subcommand>
    create      Create (or update) a pull request on an upstream GitHub
                repository.
```

### pr create

```
$ python -m bot pr create --help

usage: bot pr create [-h] -H OWNER[:REPO]:BRANCH [-B OWNER[:REPO]:BRANCH]
                     [--github-token TOKEN] [--verbose | --no-verbose]
                     [--title TITLE] [--body BODY] [--template TEMPLATE]
                     REPOSITORY

Create (or update) a pull request on an upstream GitHub repository. All
changes are expected to be already committed and pushed to the remote head
branch.

positional arguments:
  REPOSITORY            name of the (upstream) repository. one of: yt-dlp,
                        ejs, protobug, Pyinstaller-Builds, manylinux-shared,
                        dlp-bot

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (REQUIRED)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to the positional REPOSITORY argument. if
                        --base is not used, all segments will default to
                        values that are hardcoded for the given repository

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)

pull request options:
  --title TITLE         the title of the pull request. prefix the argument
                        with "file:" to load the title from a file instead
  --body BODY           the body/description of the pull request. prefix the
                        argument with "file:" to load the body from a file
                        instead
  --template TEMPLATE   a pull request template to append to the PR body.
                        prefix the argument with "file:" to load the template
                        from a file instead. if not provided, will default to
                        a hardcoded value for the given repository (if one
                        exists)
```

### tools

```
$ python -m bot tools --help

usage: bot tools [-h] <subcommand> ...

Internal bot tools.

options:
  -h, --help    show this help message and exit

tools subcommands:
  <subcommand>
    variables   Output variables needed for GitHub Actions workflows.
```

### tools variables

```
$ python -m bot tools variables --help

usage: bot tools variables [-h]
                           {actions,astring,dependencies,ejs,meriyah,protobug,user-agent}

Output variables needed for GitHub Actions workflows.

positional arguments:
  {actions,astring,dependencies,ejs,meriyah,protobug,user-agent}
                        the service for which to output variables

options:
  -h, --help            show this help message and exit
```

### update

```
$ python -m bot update --help

usage: bot update [-h] <subcommand> ...

Update actions, dependencies, etc.

options:
  -h, --help            show this help message and exit

update subcommands:
  <subcommand>
    actions (workflows)
                        Update actions in a GitHub repository's workflows.
    dependencies (deps)
                        Update dependencies for a project.
    ejs                 Update the ejs version used in yt-dlp.
    protobug            Update the protobug version used in yt-dlp.
    astring             Update the astring version used in ejs.
    meriyah             Update the meriyah version used in ejs.
    user-agent (ua)     Update the default user-agent version range used by
                        yt-dlp.
```

### update actions

```
$ python -m bot update actions --help

usage: bot update actions [-h] [-H OWNER[:REPO]:BRANCH]
                          [-B OWNER[:REPO]:BRANCH] [--pr | --no-pr]
                          [--clone | --no-clone]
                          [--use-current-worktree | --no-use-current-worktree]
                          [--verify | --no-verify] [--exclude-newer COOLDOWN]
                          [--rebase-pr | --no-rebase-pr]
                          [--overwrite-pr | --no-overwrite-pr]
                          [--pr-command-prefix PREFIX]
                          [--pr-command-allowlist NAME[,NAME...]]
                          [--git-protocol {ssh,https}] [--head-remote REMOTE]
                          [--base-remote REMOTE] [--github-token TOKEN]
                          [--commit-prefix PREFIX] [--commit-addendum MESSAGE]
                          [--commit-type {bulk,incremental}]
                          [--export-pr-body FILEPATH]
                          [--export-commit-message FILEPATH]
                          [--export-patches DIRPATH]
                          [--verbose | --no-verbose]
                          REPOSITORY [DIRECTORY]

Update actions in a GitHub repository's workflows. It is expected that the
environment has `git` available and the `actions` extra installed.

positional arguments:
  REPOSITORY            name of the (upstream) repository. one of: yt-dlp,
                        ejs, protobug, Pyinstaller-Builds
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-actions)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to the positional REPOSITORY argument. if
                        --base is not used, all segments will default to
                        values that are hardcoded for the given repository

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)
  --exclude-newer COOLDOWN
                        exclude versions newer than COOLDOWN, which can be any
                        of: ISO8601 duration (e.g. "P7D"), natural language
                        duration (e.g. "7 days"), ISO8601 timestamp (e.g.
                        "2026-03-28T23:10:22Z"), or a UNIX timestamp (seconds
                        since the epoch). an empty argument will set the
                        current timestamp as the COOLDOWN value

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

commit options:
  --commit-prefix PREFIX
                        prefix to add each to each commit subject line and to
                        the pull request title. defaults are hardcoded per
                        repository
  --commit-addendum MESSAGE
                        an addendum to add to each commit message. defaults
                        are hardcoded per repository
  --commit-type {bulk,incremental}
                        one of: "bulk" (commit changes to the current branch
                        after ALL updates), "incremental" (commit changes to
                        the current branch after EACH update). defaults to
                        "bulk" unless the --pr option is used, which defaults
                        to "incremental"

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

### update astring

```
$ python -m bot update astring --help

usage: bot update astring [-h] [-H OWNER[:REPO]:BRANCH]
                          [-B OWNER[:REPO]:BRANCH] [--pr | --no-pr]
                          [--clone | --no-clone]
                          [--use-current-worktree | --no-use-current-worktree]
                          [--verify | --no-verify]
                          [--rebase-pr | --no-rebase-pr]
                          [--overwrite-pr | --no-overwrite-pr]
                          [--pr-command-prefix PREFIX]
                          [--pr-command-allowlist NAME[,NAME...]]
                          [--git-protocol {ssh,https}] [--head-remote REMOTE]
                          [--base-remote REMOTE] [--github-token TOKEN]
                          [--commit-prefix PREFIX] [--commit-addendum MESSAGE]
                          [--export-pr-body FILEPATH]
                          [--export-commit-message FILEPATH]
                          [--export-patches DIRPATH]
                          [--verbose | --no-verbose]
                          [DIRECTORY]

Update the astring version used in ejs. It is expected that the environment
has `pnpm`, `npm`, `bun` and `deno` installed.

positional arguments:
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-astring)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to "ejs". if --base is not used, all segments
                        will default to values that are hardcoded for "ejs"

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

commit options:
  --commit-prefix PREFIX
                        prefix to add each to each commit subject line and to
                        the pull request title. defaults are hardcoded per
                        repository
  --commit-addendum MESSAGE
                        an addendum to add to each commit message. defaults
                        are hardcoded per repository

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

### update dependencies

```
$ python -m bot update dependencies --help

usage: bot update dependencies [-h] [-H OWNER[:REPO]:BRANCH]
                               [-B OWNER[:REPO]:BRANCH] [--pr | --no-pr]
                               [--clone | --no-clone]
                               [--use-current-worktree | --no-use-current-worktree]
                               [--verify | --no-verify]
                               [--rebase-pr | --no-rebase-pr]
                               [--overwrite-pr | --no-overwrite-pr]
                               [--pr-command-prefix PREFIX]
                               [--pr-command-allowlist NAME[,NAME...]]
                               [--git-protocol {ssh,https}]
                               [--head-remote REMOTE] [--base-remote REMOTE]
                               [--github-token TOKEN] [--commit-prefix PREFIX]
                               [--commit-addendum MESSAGE]
                               [--export-pr-body FILEPATH]
                               [--export-commit-message FILEPATH]
                               [--export-patches DIRPATH]
                               [--verbose | --no-verbose]
                               REPOSITORY [DIRECTORY]

Update dependencies for a project. It is expected that the environment has the
necessary package manager installed (e.g. `uv`).

positional arguments:
  REPOSITORY            name of the (upstream) repository. one of: yt-dlp,
                        ejs, Pyinstaller-Builds
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-dependencies)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to the positional REPOSITORY argument. if
                        --base is not used, all segments will default to
                        values that are hardcoded for the given repository

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

commit options:
  --commit-prefix PREFIX
                        prefix to add each to each commit subject line and to
                        the pull request title. defaults are hardcoded per
                        repository
  --commit-addendum MESSAGE
                        an addendum to add to each commit message. defaults
                        are hardcoded per repository

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

### update ejs

```
$ python -m bot update ejs --help

usage: bot update ejs [-h] [-H OWNER[:REPO]:BRANCH] [-B OWNER[:REPO]:BRANCH]
                      [--pr | --no-pr] [--clone | --no-clone]
                      [--use-current-worktree | --no-use-current-worktree]
                      [--verify | --no-verify] [--rebase-pr | --no-rebase-pr]
                      [--overwrite-pr | --no-overwrite-pr]
                      [--pr-command-prefix PREFIX]
                      [--pr-command-allowlist NAME[,NAME...]]
                      [--git-protocol {ssh,https}] [--head-remote REMOTE]
                      [--base-remote REMOTE] [--github-token TOKEN]
                      [--commit-prefix PREFIX] [--commit-addendum MESSAGE]
                      [--export-pr-body FILEPATH]
                      [--export-commit-message FILEPATH]
                      [--export-patches DIRPATH] [--verbose | --no-verbose]
                      [DIRECTORY]

Update the ejs version used in yt-dlp. It is expected that the environment has
`uv` installed.

positional arguments:
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-ejs)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to "yt-dlp". if --base is not used, all
                        segments will default to values that are hardcoded for
                        "yt-dlp"

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

commit options:
  --commit-prefix PREFIX
                        prefix to add each to each commit subject line and to
                        the pull request title. defaults are hardcoded per
                        repository
  --commit-addendum MESSAGE
                        an addendum to add to each commit message. defaults
                        are hardcoded per repository

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

### update meriyah

```
$ python -m bot update meriyah --help

usage: bot update meriyah [-h] [-H OWNER[:REPO]:BRANCH]
                          [-B OWNER[:REPO]:BRANCH] [--pr | --no-pr]
                          [--clone | --no-clone]
                          [--use-current-worktree | --no-use-current-worktree]
                          [--verify | --no-verify]
                          [--rebase-pr | --no-rebase-pr]
                          [--overwrite-pr | --no-overwrite-pr]
                          [--pr-command-prefix PREFIX]
                          [--pr-command-allowlist NAME[,NAME...]]
                          [--git-protocol {ssh,https}] [--head-remote REMOTE]
                          [--base-remote REMOTE] [--github-token TOKEN]
                          [--commit-prefix PREFIX] [--commit-addendum MESSAGE]
                          [--export-pr-body FILEPATH]
                          [--export-commit-message FILEPATH]
                          [--export-patches DIRPATH]
                          [--verbose | --no-verbose]
                          [DIRECTORY]

Update the meriyah version used in ejs. It is expected that the environment
has `pnpm`, `npm`, `bun` and `deno` installed.

positional arguments:
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-meriyah)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to "ejs". if --base is not used, all segments
                        will default to values that are hardcoded for "ejs"

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

commit options:
  --commit-prefix PREFIX
                        prefix to add each to each commit subject line and to
                        the pull request title. defaults are hardcoded per
                        repository
  --commit-addendum MESSAGE
                        an addendum to add to each commit message. defaults
                        are hardcoded per repository

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

### update protobug

```
$ python -m bot update protobug --help

usage: bot update protobug [-h] [-H OWNER[:REPO]:BRANCH]
                           [-B OWNER[:REPO]:BRANCH] [--pr | --no-pr]
                           [--clone | --no-clone]
                           [--use-current-worktree | --no-use-current-worktree]
                           [--verify | --no-verify]
                           [--rebase-pr | --no-rebase-pr]
                           [--overwrite-pr | --no-overwrite-pr]
                           [--pr-command-prefix PREFIX]
                           [--pr-command-allowlist NAME[,NAME...]]
                           [--git-protocol {ssh,https}] [--head-remote REMOTE]
                           [--base-remote REMOTE] [--github-token TOKEN]
                           [--commit-prefix PREFIX]
                           [--commit-addendum MESSAGE]
                           [--export-pr-body FILEPATH]
                           [--export-commit-message FILEPATH]
                           [--export-patches DIRPATH]
                           [--verbose | --no-verbose]
                           [DIRECTORY]

Update the protobug version used in yt-dlp. It is expected that the
environment has `uv` installed.

positional arguments:
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-protobug)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to "yt-dlp". if --base is not used, all
                        segments will default to values that are hardcoded for
                        "yt-dlp"

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

commit options:
  --commit-prefix PREFIX
                        prefix to add each to each commit subject line and to
                        the pull request title. defaults are hardcoded per
                        repository
  --commit-addendum MESSAGE
                        an addendum to add to each commit message. defaults
                        are hardcoded per repository

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

### update user-agent

```
$ python -m bot update user-agent --help

usage: bot update user-agent [-h] [-H OWNER[:REPO]:BRANCH]
                             [-B OWNER[:REPO]:BRANCH] [--pr | --no-pr]
                             [--clone | --no-clone]
                             [--use-current-worktree | --no-use-current-worktree]
                             [--verify | --no-verify]
                             [--rebase-pr | --no-rebase-pr]
                             [--overwrite-pr | --no-overwrite-pr]
                             [--pr-command-prefix PREFIX]
                             [--pr-command-allowlist NAME[,NAME...]]
                             [--git-protocol {ssh,https}]
                             [--head-remote REMOTE] [--base-remote REMOTE]
                             [--github-token TOKEN]
                             [--export-pr-body FILEPATH]
                             [--export-commit-message FILEPATH]
                             [--export-patches DIRPATH]
                             [--verbose | --no-verbose]
                             [DIRECTORY]

Update the default user-agent version range used by yt-dlp.

positional arguments:
  DIRECTORY             local path to the root of the git working tree. if not
                        provided and --clone is not used, it will default to
                        the CWD ("."). if not provided and --clone is used, it
                        will default to a temporary directory

options:
  -h, --help            show this help message and exit

remote target options:
  -H, --head OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        created from, formatted as OWNER[:REPO]:BRANCH.
                        (default: dlp-bot:bot/update-user-agent)
  -B, --base OWNER[:REPO]:BRANCH
                        label for the branch that the pull request should be
                        merged into, formatted as OWNER[:REPO]:BRANCH .if the
                        REPO segment is not included, the REPO segment will
                        default to the positional REPOSITORY argument. if
                        --base is not used, all segments will default to
                        values that are hardcoded for the given repository

update options:
  --pr, --no-pr         whether to create a pull request targeting the base
                        branch & submit it to the base owner (default: --no-
                        pr) (--pr implies: --no-use-current-worktree --no-
                        verify)
  --clone, --no-clone   whether to create a fresh clone of the repository
                        instead of using an existing local repo (default:
                        --no-clone) (--clone implies: --no-use-current-
                        worktree)
  --use-current-worktree, --no-use-current-worktree
                        whether to update/verify the local current worktree
                        instead of pulling the remote base/head branch
                        (default: --no-update-current-worktree) (--use-
                        current-worktree implies: --no-clone --no-pr)
  --verify, --no-verify
                        whether to only verify the previous update(s) instead
                        of committing update(s) (default: --no-verify)
                        (--verify implies: --no-pr)

update pull request options:
  these options are only effective if the --pr option is used

  --rebase-pr, --no-rebase-pr
                        whether to rebase an existing pull request branch on
                        the base branch (default: --no-rebase-pr) (--rebase-pr
                        implies: --no-overwrite-pr)
  --overwrite-pr, --no-overwrite-pr
                        whether to overwrite an existing pull request branch
                        with new-from-scratch updates (default: --no-
                        overwrite-pr) (--overwrite-pr implies: --no-rebase-pr)
  --pr-command-prefix PREFIX
                        the prefix for commands via pull request comments. the
                        command must be separated from the prefix by a single
                        space, e.g. "@dlp-bot overwrite" (default: @dlp-bot)
  --pr-command-allowlist NAME[,NAME...]
                        comma-separated list of usernames and/or team names
                        whose commands via pull request comments should be
                        acknowledged, e.g. "pukkandan,@yt-dlp/core". the
                        default behavior is to acknowledge commands from any
                        user

git options:
  --git-protocol {ssh,https}
                        protocol to use with git. (default: ssh)
  --head-remote REMOTE  name of the head repository's git remote in the local
                        repository. the default is "origin" if the --head
                        option is not used, otherwise the default is the OWNER
                        value from the --head argument
  --base-remote REMOTE  name of the base repository's git remote in the local
                        repository. the default is "upstream" if the --base
                        option is not used, otherwise the default is the OWNER
                        value from the --base argument

github options:
  --github-token TOKEN  GitHub API token (PAT, classic, GHA, etc) used to
                        avoid being rate-limited and to authenticate for git-
                        pushes and pull request creation. if this option is
                        not used, the value of the GH_TOKEN environment
                        variable will be used (if it is set)

export options:
  --export-pr-body FILEPATH
                        if an output filepath is provided, then export the
                        pull request body as a markdown file
  --export-commit-message FILEPATH
                        if an output filepath is provided, then export the
                        commit message to a text file
  --export-patches DIRPATH
                        if an output directory path is provided, then export
                        the commit(s) to patch file(s) in the given output
                        directory

logging options:
  --verbose, --no-verbose
                        whether to print verbose debug output, e.g. for all
                        subprocess calls and network requests (default: --no-
                        verbose)
```

