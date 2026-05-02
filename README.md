# dlp-bot
automated tools for the dlp org

## Usage
Examples:
```bash
# Update GitHub actions in CWD for yt-dlp repo:
python -m bot actions yt-dlp

# Update yt-dlp actions in another location, push to fork, and create PR:
python -m bot actions --pr --head my_gh_username:my_branch yt-dlp /path/to/yt-dlp

# To update and create a PR in separate steps:
python -m bot actions --commit-type=incremental --export-pr-body artifacts/pr.md --export-commit-message artifacts/commit.txt ejs
git push origin HEAD:my_branch
python -m bot pr --head my_gh_username:my_branch --body file:artifacts/pr.md --title file:artifacts/commit.txt ejs
```
