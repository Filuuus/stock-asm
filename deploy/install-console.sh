#!/bin/bash
# Puts the status screen on the monitor: sudo bash /srv/agrostma/app/deploy/install-console.sh
set -euo pipefail
cp /srv/agrostma/app/deploy/agrostma-console.service /etc/systemd/system/
systemctl daemon-reload
systemctl mask --now getty@tty1.service
systemctl enable agrostma-console.service
systemctl restart agrostma-console.service
systemctl --no-pager status agrostma-console.service | head -5
