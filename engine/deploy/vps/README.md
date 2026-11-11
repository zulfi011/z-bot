# Running the bot on your own small server (AWS Lightsail, fixed IP)

What you end up with: a small Ubuntu server in Frankfurt with a **fixed IP address**, running the bot 24/7,
restarting itself after crashes and reboots, backing up its database every night, and a private dashboard only your
phone and Mac can open. Your money never leaves Binance — the bot only sends buy/sell orders there.

Why a fixed IP: Binance lets you lock your API key to one IP address, so a stolen key is useless anywhere else.
Why Frankfurt: Binance.com refuses API calls from the US (and restricts Japan, Singapore and the UK).

Cost: about **$5 a month** (the Lightsail plan that includes a public IPv4; the $7 plan with 2 GB RAM is more
comfortable). Time: about 30–45 minutes. Commands below are pasted into the Mac **Terminal** app.

---

## 1. Create the AWS account

1. Go to <https://aws.amazon.com> → **Create an AWS account** (email, password, card and phone verification).
2. Sign in and open <https://lightsail.aws.amazon.com>.
3. Safety net (this is only an email alarm, not a charge): AWS console → **Billing and Cost Management → Budgets →
   Create budget → Monthly cost budget** of **$1** with your email, so you hear about any charge at all.

## 2. Make your login key on the Mac (once)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/z-bot -C "z-bot"
```

Choose a passphrase. You will upload the **public** file `~/.ssh/z-bot.pub`. Never share the private file
`~/.ssh/z-bot`.

## 3. Create the server

In Lightsail → **Create instance**:

1. **Region:** Frankfurt (eu-central-1).
2. **Platform:** Linux/Unix. **Blueprint:** OS Only → **Ubuntu 24.04 LTS**.
3. **SSH key pair:** Change SSH key pair → **Upload new** → choose `~/.ssh/z-bot.pub`
   (in the file picker press Cmd+Shift+. to show hidden folders).
4. **Plan:** the $5 plan with public IPv4 (or $7 for 2 GB RAM). If the plan shows **"First 3 months free"**, pick it.
5. **Name:** `z-bot` → **Create instance**. Wait until it says **Running**.

## 4. Give it a fixed IP and close unneeded ports

1. Lightsail → **Networking → Create static IP** → attach it to `z-bot` → name it `z-bot-ip`.
   This address (e.g. `3.121.x.x`) is your **fixed IP**. It is free while attached.
2. Open the instance → **Networking** tab → IPv4 firewall: keep **SSH (22)**, **delete HTTP (80)**. The dashboard is
   reached privately through Tailscale (step 8), not through open ports.

## 5. First login

```bash
ssh -i ~/.ssh/z-bot ubuntu@STATIC_IP
```

Type `yes` the first time, then your passphrase. `exit` returns to the Mac.

## 6. Install everything with one script

From the Mac:

```bash
cd z-bot/engine
scp -i ~/.ssh/z-bot deploy/vps/setup.sh ubuntu@STATIC_IP:/home/ubuntu/setup.sh
ssh -i ~/.ssh/z-bot ubuntu@STATIC_IP "sudo bash /home/ubuntu/setup.sh git@github.com:YOUR_USER/z-bot.git"
```

The script installs security updates and Docker, adds swap, creates a `bot` user with your key, turns off
password logins, allows only SSH through the firewall, downloads the app to `/opt/z-bot` (the bot runs from `/opt/z-bot/engine`), writes a private
settings file with a random database password and dashboard control key, and schedules nightly backups.

**The first run stops** and prints a line starting `ssh-ed25519 … z-bot-server` — a **read-only deploy key**
so the server can download your private code. Add it in GitHub → your copy of the repo → **Settings → Deploy keys →
Add deploy key** (leave "Allow write access" **off**), then run the same `ssh … setup.sh …` command again.

At the end it prints the server IP and your **dashboard control key** — save the key in your password manager.

## 7. Start the bot

```bash
ssh -i ~/.ssh/z-bot bot@STATIC_IP "cd /opt/z-bot/engine && docker compose up -d --build"
ssh -i ~/.ssh/z-bot bot@STATIC_IP "cd /opt/z-bot/engine && docker compose ps"
```

Services should show `running`/`healthy` (`migrate` shows `exited (0)`, which is normal). The first start downloads
about 32 days of prices per coin, which takes a few minutes.

## 8. Open the dashboard privately on your phone (Tailscale, free)

1. Create a Tailscale account at <https://tailscale.com>; install the app on your phone and Mac and sign in.
2. On the server:
   ```bash
   ssh -i ~/.ssh/z-bot bot@STATIC_IP
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   sudo tailscale serve --bg --https=443 http://127.0.0.1:3000
   tailscale serve status
   ```
   Approve the server with the link `tailscale up` prints (and allow HTTPS certificates if asked).
3. Open the `https://z-bot.<your-tailnet>.ts.net` address on your phone and add it to the home screen.
4. Dashboard → **System health → "Binance trading API"** must say **reachable** and show your static IP.

## 9. Binance API key

1. Binance → **API Management → Create API → System generated**, give it a name.
2. Permissions: **Enable Reading** and **Enable Spot & Margin Trading**. **Withdrawals: never** — the bot refuses a
   key that can withdraw.
3. **Restrict access to trusted IPs only** → your static IP from step 4.
4. Open the dashboard (step 8) → **Attach Binance account** → paste the API key and secret. The bot checks the key
   with Binance and keeps it only on the server, never in the database or in `.env`.
5. Trading stays in **Shadow** until you press **Go live**.

---

## Everyday commands

```bash
ssh -i ~/.ssh/z-bot bot@STATIC_IP                          # log in
cd /opt/z-bot/engine && docker compose logs -f worker               # watch the bot (Ctrl+C stops watching)
cd /opt/z-bot/engine && git pull && docker compose up -d --build    # install an update pushed to GitHub
cd /opt/z-bot/engine && docker compose restart worker               # restart only the bot
ls /opt/z-bot/engine/backups                                        # nightly database backups
```

## If something goes wrong

| Problem | Fix |
|---|---|
| `Permission denied (publickey)` | Use `-i ~/.ssh/z-bot`, the right user (`ubuntu` before setup, `bot` after) and the static IP. |
| `Connection timed out` | Instance must be Running; SSH (22) must be allowed in the instance's Networking tab. |
| Setup stopped and printed a key | Expected on the first run — add it as a GitHub deploy key (step 6), run again. |
| Dashboard won't open on the phone | Tailscale must be on and signed in on the phone; check `tailscale serve status` on the server. |
| "Binance trading API: blocked" | The server is in a restricted region — recreate it in Frankfurt. |
