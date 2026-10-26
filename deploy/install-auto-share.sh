#!/bin/bash
# One-time read-write mount of the Compartidos\Auto folder on the office file server at /mnt/auto, where
# the app writes what it generates on its own: the Excel workbooks staff open directly (Corte de Caja now;
# Comisiones later). Separate from the read-only Compartidos mount (install-share.sh) and with its own
# Windows account, which can write only in Auto; staff can only read there.
# Needs in backend/.env: AUTO_SHARE (//192.168.1.134/Compartidos/Auto), AUTO_SHARE_USER and
# AUTO_SHARE_PASSWORD; the login is moved to a root-only file.
# Run on the server: sudo bash /srv/agrostma/app/deploy/install-auto-share.sh
set -euo pipefail
MOUNT=/mnt/auto
CREDS=/etc/agrostma/auto-share.cred
ENV=/srv/agrostma/app/backend/.env

apt-get install -y cifs-utils

share=$(sed -n 's/^AUTO_SHARE=//p' "$ENV")
[ -n "$share" ] || { echo "Add AUTO_SHARE to $ENV first." >&2; exit 1; }
if [ ! -s "$CREDS" ]; then
    user=$(sed -n 's/^AUTO_SHARE_USER=//p' "$ENV")
    pass=$(sed -n 's/^AUTO_SHARE_PASSWORD=//p' "$ENV")
    [ -n "$user" ] && [ -n "$pass" ] || { echo "Add AUTO_SHARE_USER and AUTO_SHARE_PASSWORD to $ENV first." >&2; exit 1; }
    install -d -m 700 /etc/agrostma
    (umask 077; printf 'username=%s\npassword=%s\n' "$user" "$pass" > "$CREDS")
fi
sed -i '/^AUTO_SHARE_USER=/d; /^AUTO_SHARE_PASSWORD=/d' "$ENV"

install -d "$MOUNT"
OPTS="credentials=$CREDS,rw,uid=agrostma,gid=agrostma,file_mode=0664,dir_mode=0775,iocharset=utf8"
OPTS="$OPTS,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30"
sed -i "\|[[:space:]]$MOUNT[[:space:]]|d" /etc/fstab
echo "$share $MOUNT cifs $OPTS 0 0" >> /etc/fstab
systemctl daemon-reload
systemctl restart "$(systemd-escape -p --suffix=automount "$MOUNT")"

EXPORT_DIR="$MOUNT/Corte de Caja"
grep -q "^CORTE_DE_CAJA_EXPORT_DIR=" "$ENV" && sed -i "s|^CORTE_DE_CAJA_EXPORT_DIR=.*|CORTE_DE_CAJA_EXPORT_DIR=$EXPORT_DIR|" "$ENV" \
    || echo "CORTE_DE_CAJA_EXPORT_DIR=$EXPORT_DIR" >> "$ENV"
systemctl restart agrostma-django   # the page's button writes from the web process

sudo -u agrostma touch "$MOUNT/.write-test" && rm "$MOUNT/.write-test" && echo "Write OK in $MOUNT"
