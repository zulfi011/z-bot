#!/usr/bin/env bash
# Daily public-stats job (cron). Exports percentages only and pushes them to the public repo.
# It reads the database through a read-only role and never restarts, rebuilds or writes to the bot.
# If anything here fails, trading is unaffected; the page just keeps yesterday's numbers.
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/z-bot}"
STATS_HOME="${STATS_HOME:-$HOME/z-bot-stats}"
REPO_DIR="$STATS_HOME/repo"
KEY="$STATS_HOME/deploy_key"

exec 9>"$STATS_HOME/.lock"
flock -n 9 || exit 0   # a run is already going

export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
cd "$REPO_DIR"
git pull -q --rebase origin main

nice -n 19 ionice -c3 timeout 120 \
  python3 "$COMPOSE_DIR/deploy/public_stats/export_stats.py" --compose-dir "$COMPOSE_DIR" --out docs/stats.json

git add docs/stats.json
if git diff --cached --quiet; then
  exit 0
fi
git -c user.name="Z-Bot stats" -c user.email="stats@z-bot.invalid" commit -q -m "Live stats $(date -u +%F)"
git push -q origin main
