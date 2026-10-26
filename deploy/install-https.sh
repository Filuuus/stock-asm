#!/bin/bash
# One-time HTTPS setup for https://interno.agrostma.com (the office address). Gets a Let's Encrypt
# certificate through a Cloudflare DNS challenge, so the server never has to be reachable from the
# internet; certbot's own timer renews it and reloads nginx.
# Needs a Cloudflare API token limited to Zone -> DNS -> Edit on agrostma.com; it's asked for below
# and stored readable by root only.
# Run on the server: sudo bash /srv/agrostma/app/deploy/install-https.sh
set -euo pipefail
cd "$(dirname "$0")"
DOMAIN=interno.agrostma.com
CREDS=/etc/letsencrypt/cloudflare.ini

apt-get install -y certbot python3-certbot-dns-cloudflare

if [ ! -s "$CREDS" ]; then
    read -rsp "Cloudflare API token (DNS edit on agrostma.com): " token; echo
    install -d -m 700 /etc/letsencrypt
    (umask 077; printf 'dns_cloudflare_api_token = %s\n' "$token" > "$CREDS")
fi

certbot certonly --non-interactive --agree-tos --register-unsafely-without-email \
    --dns-cloudflare --dns-cloudflare-credentials "$CREDS" --dns-cloudflare-propagation-seconds 30 \
    --deploy-hook 'systemctl reload nginx' -d "$DOMAIN"

# Django must accept the new hostname.
ENV=/srv/agrostma/app/backend/.env
grep -q "^DJANGO_ALLOWED_HOSTS=.*$DOMAIN" "$ENV" || sed -i "s/^DJANGO_ALLOWED_HOSTS=.*/&,$DOMAIN/" "$ENV"
systemctl restart agrostma-django

install -m 644 nginx.conf /etc/nginx/sites-available/agrostma
nginx -t
systemctl reload nginx
ufw allow from 192.168.1.0/24 to any port 443 proto tcp

certbot certificates -d "$DOMAIN"
systemctl list-timers certbot.timer --no-pager
