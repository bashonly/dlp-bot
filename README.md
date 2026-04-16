# dlp-bot
automated tools for the dlp org

## Usage
Examples:
```bash
# Update GitHub actions in CWD for yt-dlp repo:
bot actions yt-dlp

# Update yt-dlp actions in another location, push to fork, and create PR:
bot actions --pr --head my_gh_username:my_branch yt-dlp /path/to/yt-dlp

# To update and create a PR in separate steps:
bot actions --commit-type=incremental --export-pr dist/ ejs
git push origin my_branch
bot pr --head my_gh_username:my_branch --body file:dist/pull-request.bot.md --title file:dist/commit-message.bot.txt ejs
```
