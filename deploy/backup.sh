#!/bin/bash
# Nightly backups, run as agrostma by agrostma-backup.timer:
#   1. App data (SQLite database, product photos, exports) -> a dated snapshot on the backup SSD.
#   2. Compartidos\Contabilidad -> a dated snapshot on the backup SSD.
#   3. The same app data -> Compartidos\Auto\Respaldos on servercompac, so a copy lives off this machine.
# Snapshots hard-link files that didn't change since the previous one, so each day only costs what changed.
set -euo pipefail

APP=${APP:-/srv/agrostma/app}
SSD=${SSD:-/srv/backups}
OFFSITE=${OFFSITE:-/mnt/auto/Respaldos}
KEEP_DAYS=30
today=$(date +%F)
cutoff=$(date -d "-$KEEP_DAYS days" +%F)

# snapshot <dest root> <source>... : $root/<today> becomes a full copy of the sources.
snapshot() {
    local root=$1 last; shift
    mkdir -p "$root"
    last=$(find "$root" -mindepth 1 -maxdepth 1 -name '20??-??-??' ! -name "$today" | sort | tail -1)
    # u+w: the share's files are read-only (0440/0550), and old snapshots must stay deletable.
    rsync -a --delete --chmod=u+w ${last:+--link-dest="$last"} "$@" "$root/$today.partial/"
    rm -rf "$root/$today"
    mv "$root/$today.partial" "$root/$today"
    for dir in "$root"/20??-??-??; do
        [[ $(basename "$dir") < $cutoff ]] && rm -rf "$dir"
    done
    echo "$root/$today: $(du -sh "$root/$today" | cut -f1)"
}

# A consistent copy of the database even while the app writes to it.
staging=$SSD/.staging
mkdir -p "$staging"
python3 -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' \
    "$APP/backend/db.sqlite3" "$staging/db.sqlite3"

app_data=("$staging/db.sqlite3" "$APP/frontend/public/products" "$APP/backend/exports")
snapshot "$SSD/app" "${app_data[@]}"
snapshot "$SSD/Contabilidad" /mnt/compartidos/Contabilidad/

# Off this machine. The Respaldos folder is created by hand with an ACL that hides it from staff (the database
# holds password hashes); creating it here would inherit Auto's read-for-everyone permission.
[ -d "$OFFSITE" ] || { echo "$OFFSITE is missing; create it on servercompac first." >&2; exit 1; }
mkdir -p "$OFFSITE/base de datos"
cp "$staging/db.sqlite3" "$OFFSITE/base de datos/db-$today.sqlite3"
find "$OFFSITE/base de datos" -name 'db-*.sqlite3' ! -newermt "$cutoff" -delete
# SMB: no owners, permissions or hard links, and coarse timestamps.
rsync -rt --delete --modify-window=2 "$APP/frontend/public/products" "$APP/backend/exports" "$OFFSITE/archivos/"
echo "$OFFSITE: db-$today.sqlite3 + archivos"
