# Public stats

Once a day the server publishes the bot's results to the public page at
`https://zulfi011.github.io/z-bot/`. **Percentages only**: no dollar amounts, balances, quantities or pot size ever
leave the server.

## How it stays out of the bot's way

- **Nothing in the bot changes.** No code, container, restart or rebuild. These files sit in the repo and are only
  run by a cron job.
- **Read-only database login** (`zbot_stats`, from `create_readonly_role.sql`):
  - It can only `SELECT` from `trades`, `positions`, `account_snapshots` and `candles_1m`.
  - Every transaction it opens is read-only, and every query stops after 20 seconds.
  - It has no password, so it can't log in over the network, only from inside the db container.
- **Low priority:** the job runs once a day at 00:30 UTC with `nice` and `ionice`. It finishes in seconds and is
  killed after 2 minutes.
- **Safe to fail:** if it breaks, the page keeps yesterday's numbers and trading carries on as normal.
- **Allow-list:** `export_stats.py` lists every field it may publish. Any other field, or anything named like
  money, stops the export.
- **Narrow GitHub access:** the job pushes with a deploy key that can write to the `z-bot` repo only.

The account's trades are counted from the day it first traded live, and the shadow trades it makes after its last live
minute; older shadow lots from before that day are left out. Order ids are never published.

## One-time setup

### On your Mac

1. On GitHub, create the repo **`zulfi011/z-bot`**: **Public**, with no README, licence or .gitignore.
2. Push the prepared public folder:

   ```bash
   cd path/to/your-stats-repo && git remote add origin https://github.com/zulfi011/z-bot.git && git push -u origin main
   ```

3. In the repo, go to **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, folder = `/docs`,
   then **Save**.
4. In the repo, go to **Settings → General → Social preview** and upload `docs/social-preview.png`.
5. Push the bot repo, which now contains this folder:

   ```bash
   cd path/to/z-bot && git push
   ```

### On the server

Connect:

```bash
ssh -i ~/.ssh/z-bot bot@STATIC_IP
```

Get the new files. This is a `git pull` only. Without `--build` nothing restarts:

```bash
cd /opt/z-bot/engine && git pull
```

Create the read-only database login:

```bash
cd /opt/z-bot/engine && docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < deploy/public_stats/create_readonly_role.sql
```

Make a key that can push to the public repo only:

```bash
mkdir -p ~/z-bot-stats && ssh-keygen -t ed25519 -N "" -C "z-bot-stats" -f ~/z-bot-stats/deploy_key && cat ~/z-bot-stats/deploy_key.pub
```

Copy the line it prints. On GitHub, go to **zulfi011/z-bot → Settings → Deploy keys → Add deploy key**, paste the
line, title it `server stats`, tick **Allow write access**, and click **Add key**.

Clone the public repo with that key:

```bash
GIT_SSH_COMMAND="ssh -i ~/z-bot-stats/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" git clone git@github.com:zulfi011/z-bot.git ~/z-bot-stats/repo
```

Run it once by hand:

```bash
/opt/z-bot/engine/deploy/public_stats/run_export.sh && tail -c 400 ~/z-bot-stats/repo/docs/stats.json
```

Schedule it daily at 00:30 UTC:

```bash
(crontab -l 2>/dev/null; echo '30 0 * * * /opt/z-bot/engine/deploy/public_stats/run_export.sh >> $HOME/z-bot-stats/export.log 2>&1') | crontab -
```

## Checking on it

- The page: `https://zulfi011.github.io/z-bot/`
- The last run: `tail -20 ~/z-bot-stats/export.log`
- To stop publishing: `crontab -e` and delete the line. The bot is unaffected either way.
