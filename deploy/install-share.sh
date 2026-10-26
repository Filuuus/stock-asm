#!/bin/bash
# One-time mount of the office file server's "Compartidos" share at /mnt/compartidos, read-only, so the
# app can read the accountant's workbooks (import_vehicle_reports reads Contabilidad/<year>/Reportes
# Mensuales <year>.xlsx). Mounted on first access and skipped at boot if the file server is down.
# Credentials come from SHARE_USER / SHARE_PASSWORD in backend/.env; they're moved to a root-only file.
# Run on the server: sudo bash /srv/agrostma/app/deploy/install-share.sh
set -euo pipefail
SHARE=//192.168.1.134/Compartidos   # servercompac; same machine as the ERP's SQL Server
MOUNT=/mnt/compartidos
CREDS=/etc/agrostma/share.cred
ENV=/srv/agrostma/app/backend/.env

apt-get install -y cifs-utils

if [ ! -s "$CREDS" ]; then
    user=$(sed -n 's/^SHARE_USER=//p' "$ENV")
    pass=$(sed -n 's/^SHARE_PASSWORD=//p' "$ENV")
    [ -n "$user" ] && [ -n "$pass" ] || { echo "Add SHARE_USER and SHARE_PASSWORD to $ENV first." >&2; exit 1; }
    install -d -m 700 /etc/agrostma
    (umask 077; printf 'username=%s\npassword=%s\n' "$user" "$pass" > "$CREDS")
fi
sed -i '/^SHARE_USER=/d; /^SHARE_PASSWORD=/d' "$ENV"

install -d "$MOUNT"
OPTS="credentials=$CREDS,ro,uid=agrostma,gid=agrostma,file_mode=0440,dir_mode=0550,iocharset=utf8"
OPTS="$OPTS,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30"
sed -i "\|[[:space:]]$MOUNT[[:space:]]|d" /etc/fstab
echo "$SHARE $MOUNT cifs $OPTS 0 0" >> /etc/fstab
systemctl daemon-reload
systemctl restart "$(systemd-escape -p --suffix=automount "$MOUNT")"

grep -q "^VEHICLE_REPORTS_DIR=" "$ENV" && sed -i "s|^VEHICLE_REPORTS_DIR=.*|VEHICLE_REPORTS_DIR=$MOUNT/Contabilidad|" "$ENV" \
    || echo "VEHICLE_REPORTS_DIR=$MOUNT/Contabilidad" >> "$ENV"

ls "$MOUNT/Contabilidad/$(date +%Y)"
