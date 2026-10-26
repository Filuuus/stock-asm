#!/bin/bash
# Installs or refreshes the systemd services and the nginx site from this folder.
# Run on the server: sudo bash /srv/agrostma/app/deploy/install-services.sh
set -euo pipefail
cd "$(dirname "$0")"

install -m 644 agrostma-django.service agrostma-next.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable agrostma-django agrostma-next
systemctl restart agrostma-django agrostma-next

install -m 644 agrostma-fleet-daily.service agrostma-fleet-daily.timer \
    agrostma-fleet-monthly.service agrostma-fleet-monthly.timer \
    agrostma-corte-export.service agrostma-corte-export.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now agrostma-fleet-daily.timer agrostma-fleet-monthly.timer agrostma-corte-export.timer

# nginx.conf needs the interno.agrostma.com certificate. Stop before touching nginx without it: a config
# that fails nginx -t would stay on disk and keep nginx from starting at the next reboot.
[ -e /etc/letsencrypt/live/interno.agrostma.com/fullchain.pem ] || { echo 'Run install-https.sh first.' >&2; exit 1; }
install -m 644 nginx.conf /etc/nginx/sites-available/agrostma
ln -sf /etc/nginx/sites-available/agrostma /etc/nginx/sites-enabled/agrostma
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

ufw allow from 192.168.1.0/24 to any port 80 proto tcp

systemctl --no-pager --lines=0 status agrostma-django agrostma-next nginx
systemctl --no-pager list-timers 'agrostma-*'
