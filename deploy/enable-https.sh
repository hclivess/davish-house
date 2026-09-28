#!/usr/bin/env bash
# Turn on HTTPS for davishshouse.com once its DNS A records point at this server.
# Usage (as root):  deploy/enable-https.sh [email-for-letsencrypt]
set -euo pipefail
DOMAIN=davishshouse.com
EMAIL="${1:-cyphernormie@gmail.com}"
MYIP=$(curl -s https://api.ipify.org)
for h in "$DOMAIN" "www.$DOMAIN"; do
  got=$(dig +short "$h" A @1.1.1.1 | tail -1)
  if [ "$got" != "$MYIP" ]; then
    echo "DNS for $h resolves to '${got:-nothing}' but this server is $MYIP. Fix the A record and wait for it to propagate, then re-run." >&2
    exit 1
  fi
done
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
# Canonical host + secure cookies for the app.
sed -i "s|^DAVISH_BASE_URL=.*|DAVISH_BASE_URL=https://$DOMAIN|" /etc/davish/env
systemctl restart davish
nginx -t && systemctl reload nginx
echo "HTTPS is live: https://$DOMAIN  (certificates renew automatically via certbot.timer)"
echo "Now set the Stripe webhook URL to https://$DOMAIN/stripe/webhook"
