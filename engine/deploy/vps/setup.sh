#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 VPS for Z-Bot.
# Run with sudo from the login user ('ubuntu' on AWS Lightsail) or as root:
#   sudo bash setup.sh git@github.com:YOUR_USER/YOUR_REPO.git
# Safe to re-run. It never prints or asks for Binance keys.
set -euo pipefail

APP_DIR=/opt/z-bot
# The repository is cloned to APP_DIR; the bot itself (docker-compose.yml, .env) lives in its engine/ folder.
ENGINE_DIR="$APP_DIR/engine"
REPO="${1:?Usage: bash setup.sh git@github.com:YOUR_USER/YOUR_REPO.git}"
BOT_USER=bot
# The SSH key you logged in with ('ubuntu' on Lightsail, root on most other providers).
LOGIN_HOME=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)

echo "== 1/7 System updates and automatic security patches"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades docker.io docker-compose-v2
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== 2/7 Swap (lets a 1 GB server build the images)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "== 3/7 Non-root user '$BOT_USER' with your SSH key"
id "$BOT_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$BOT_USER"
usermod -aG sudo,docker "$BOT_USER"
install -d -m 700 -o "$BOT_USER" -g "$BOT_USER" /home/$BOT_USER/.ssh
install -m 600 -o "$BOT_USER" -g "$BOT_USER" "$LOGIN_HOME/.ssh/authorized_keys" /home/$BOT_USER/.ssh/authorized_keys
echo "$BOT_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-$BOT_USER

echo "== 4/7 SSH: keys only, no root password logins"
# sshd uses the first value it reads and includes sshd_config.d/ first, so a 00- file wins over provider files.
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' > /etc/ssh/sshd_config.d/00-z-bot.conf
mkdir -p /run/sshd   # Ubuntu 24.04 starts sshd on demand, so this folder may not exist yet
sshd -t
systemctl restart ssh || systemctl restart sshd || true

echo "== 5/7 Firewall: only SSH is open to the internet"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable
systemctl enable --now fail2ban docker

echo "== 6/7 App code (private repo, read-only deploy key) and private settings"
KEY=/home/$BOT_USER/.ssh/github_deploy
if [ ! -f "$KEY" ]; then
  sudo -u "$BOT_USER" ssh-keygen -t ed25519 -N "" -f "$KEY" -C "z-bot-server" >/dev/null
  sudo -u "$BOT_USER" bash -c "printf 'Host github.com\n  IdentityFile $KEY\n  IdentitiesOnly yes\n' >> /home/$BOT_USER/.ssh/config"
  sudo -u "$BOT_USER" bash -c "ssh-keyscan -t ed25519 github.com >> /home/$BOT_USER/.ssh/known_hosts 2>/dev/null"
fi
install -d -o "$BOT_USER" -g "$BOT_USER" "$APP_DIR"
if [ ! -d "$APP_DIR/.git" ] && ! sudo -u "$BOT_USER" git clone "$REPO" "$APP_DIR"; then
  echo
  echo "GitHub refused the download. Add this READ-ONLY deploy key to the repo, then re-run this script:"
  echo "  GitHub → your repo → Settings → Deploy keys → Add deploy key (leave 'Allow write access' OFF)"
  echo
  cat "$KEY.pub"
  exit 1
fi
if [ ! -f "$ENGINE_DIR/.env" ]; then
  cat > "$ENGINE_DIR/.env" <<EOF
POSTGRES_DB=papertrading
POSTGRES_USER=paperbot
POSTGRES_PASSWORD=$(openssl rand -hex 24)
STRATEGY_EDIT_TOKEN=$(openssl rand -hex 16)
# The dashboard is only reachable on this machine; Tailscale publishes it privately to your devices.
WEB_BIND_ADDRESS=127.0.0.1
WEB_PORT=3000
LOG_LEVEL=INFO
# Attach your Binance key from the dashboard (Attach Binance account); it is never stored in this file.
EOF
  chown "$BOT_USER":"$BOT_USER" "$ENGINE_DIR/.env"
  chmod 600 "$ENGINE_DIR/.env"
fi

echo "== 7/7 Nightly database backup (kept 14 days)"
install -d -m 700 -o "$BOT_USER" -g "$BOT_USER" "$ENGINE_DIR/backups"
cat > /etc/cron.d/z-bot-backup <<EOF
15 3 * * * $BOT_USER cd $ENGINE_DIR && docker compose exec -T db pg_dump -U paperbot papertrading | gzip > backups/db-\$(date +\%F).sql.gz && find backups -name 'db-*.sql.gz' -mtime +14 -delete
EOF

echo
echo "Done. This server's fixed public IPv4 (use it in Binance → API → trusted IPs):"
curl -4 -s https://ifconfig.me || true
echo
echo "Your dashboard control key (keep it private):"
grep STRATEGY_EDIT_TOKEN "$ENGINE_DIR/.env" | cut -d= -f2
echo
echo "Next: follow engine/deploy/vps/README.md step 7 (start the app) and step 8 (Tailscale)."
