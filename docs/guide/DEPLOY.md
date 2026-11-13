# Run it on a server

On your own computer Z-Bot works out of the box (see the [Quickstart](../../README.md#quickstart-5-minutes-no-account-needed)).
To trade live around the clock, run it on a small always-on server instead.

## What Binance requires

Binance only accepts API trading from some places, and a trading key should be locked to one address:

- **A fixed public IPv4 address.** Binance's API-key IP list only understands IPv4, and a home connection's address
  usually changes. Cloud servers give you a fixed ("static") one.
- **A region where Binance.com allows API trading.** The US, the UK, Japan and Singapore are refused. Frankfurt
  (AWS `eu-central-1`) works.
- **A key with reading and spot trading only, restricted to that IP.** Never enable withdrawals; Z-Bot refuses keys
  that can withdraw.

The dashboard checks this for you: **System health → Binance trading API** says whether Binance accepts requests from
where the bot runs, and the Attach Binance popup shows the server's public IP to copy into Binance.

## The short version

1. Rent a small Linux server with a static IPv4 in an allowed region (1–2 GB of memory is enough).
2. Run the setup script. It hardens SSH, turns on the firewall (SSH only), installs Docker, downloads Z-Bot to
   `/opt/z-bot`, writes a private settings file with a random database password and a dashboard **control key**,
   and schedules nightly database backups.
3. Start it: `cd /opt/z-bot/engine && docker compose up -d --build`.
4. Reach the dashboard **privately**: an SSH tunnel (`ssh -L 3000:127.0.0.1:3000 you@server`, then open the dashboard in
   your browser) or a private network such as Tailscale. Never open the dashboard's port to the internet.
5. Unlock the dashboard once with the control key the script printed.
6. **Attach Binance account**, then press **Go live** when you are ready.

Step-by-step, with screenshots-level detail for AWS Lightsail: [engine/deploy/vps/README.md](../../engine/deploy/vps/README.md).

## Updating

```bash
cd /opt/z-bot && git pull && cd engine && docker compose up -d --build
```

Database changes run automatically before the API starts. Open lots and their Binance stops are not affected by a
restart: the bot picks up where it left off.

## Publishing your own results (optional)

`engine/deploy/public_stats/` publishes a daily, percentages-only summary of your account's trades to a GitHub Pages site,
through a read-only database login and a deploy key that can write to one repository only. See its
[README](../../engine/deploy/public_stats/README.md).
