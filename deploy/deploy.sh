#!/usr/bin/env bash
# Install or update the Davish's House service on this host. Idempotent. Run as root from the repo:  deploy/deploy.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/srv/davish

id -u davish >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin davish
mkdir -p "$APP" /var/lib/davish/uploads /etc/davish /var/www/certbot

# Code
rsync -a --delete --exclude .venv --exclude '*.db*' --exclude __pycache__ --exclude .pytest_cache --exclude tests "$SRC/" "$APP/"
[ -x "$APP/.venv/bin/python" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/python" -m pip install -q -r "$APP/requirements.txt"

# Config (never overwrite an existing env)
if [ ! -f /etc/davish/env ]; then
  sed "s|^DAVISH_SECRET=.*|DAVISH_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')|" "$SRC/deploy/env.example" > /etc/davish/env
  chmod 600 /etc/davish/env
fi
chown -R davish:davish "$APP" /var/lib/davish
chmod 755 /var/lib/davish /var/lib/davish/uploads   # nginx (www-data) reads uploads

# Service
install -m 644 "$SRC/deploy/davish.service" /etc/systemd/system/davish.service
systemctl daemon-reload
systemctl enable --now davish >/dev/null
systemctl restart davish

# Nginx
install -m 644 "$SRC/deploy/davish-proxy.conf" /etc/nginx/snippets/davish-proxy.conf
install -m 644 "$SRC/deploy/nginx-davish.conf" /etc/nginx/sites-available/davish.conf
ln -sf /etc/nginx/sites-available/davish.conf /etc/nginx/sites-enabled/davish.conf
nginx -t && systemctl reload nginx

sleep 1
systemctl --no-pager --lines=0 status davish | sed -n 1,3p
curl -fsS -o /dev/null -w "app health: HTTP %{http_code}\n" http://127.0.0.1:8100/api/health
