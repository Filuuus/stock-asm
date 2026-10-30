#!/bin/bash
# Formats the backup SSD (only if it's blank), mounts it at /srv/backups, creates the Contpaqi volume on the HDD
# (free space in the system's LVM group, so the system volume isn't touched) and installs the nightly backup timer.
# Run on the server: sudo bash /srv/agrostma/app/deploy/install-backups.sh /dev/sdX
set -euo pipefail
cd "$(dirname "$0")"
MOUNT=/srv/backups

if ! mountpoint -q "$MOUNT"; then
    disk=${1:?Usage: install-backups.sh /dev/sdX (the backup SSD; see lsblk)}
    # Refuse anything that isn't a blank disk: a wrong letter here would wipe the system drive.
    [ "$(lsblk -dno TYPE "$disk")" = disk ] || { echo "$disk is not a whole disk." >&2; exit 1; }
    [ -z "$(lsblk -no FSTYPE,PARTTYPE "$disk" | tr -d '[:space:]')" ] && [ "$(lsblk -no NAME "$disk" | wc -l)" = 1 ] \
        || { echo "$disk has partitions or a filesystem; not touching it." >&2; exit 1; }
    lsblk -o NAME,SIZE,MODEL "$disk"
    read -rp "Format $disk as the backup disk? Everything on it is erased. [y/N] " answer
    [ "$answer" = y ] || exit 1
    mkfs.ext4 -q -L respaldos "$disk"
    uuid=$(blkid -s UUID -o value "$disk")
    mkdir -p "$MOUNT"
    grep -q "$uuid" /etc/fstab || echo "UUID=$uuid $MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab
    systemctl daemon-reload
    mount "$MOUNT"
fi

CONTPAQI_MOUNT=/srv/backups-contpaqi
CONTPAQI_LV=/dev/ubuntu-vg/contpaqi
if [ ! -e "$CONTPAQI_LV" ]; then
    lvcreate -q -L 200G -n contpaqi ubuntu-vg
    mkfs.ext4 -q -L contpaqi "$CONTPAQI_LV"
fi
mkdir -p "$CONTPAQI_MOUNT"
grep -q "$CONTPAQI_LV" /etc/fstab || echo "$CONTPAQI_LV $CONTPAQI_MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab
systemctl daemon-reload
mountpoint -q "$CONTPAQI_MOUNT" || mount "$CONTPAQI_MOUNT"

chown agrostma:agrostma "$MOUNT" "$CONTPAQI_MOUNT"
chmod 750 "$MOUNT" "$CONTPAQI_MOUNT"

install -m 644 agrostma-backup.service agrostma-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now agrostma-backup.timer
df -h "$MOUNT" "$CONTPAQI_MOUNT"
systemctl --no-pager list-timers agrostma-backup.timer
