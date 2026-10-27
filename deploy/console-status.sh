#!/bin/bash
# One screen of server status for the monitor on tty1, redrawn by `watch` (agrostma-console.service).
# Read-only: runs as an unprivileged dynamic user and only queries systemd, the disks and the local web server.

ok()  { printf '\e[32m  OK  \e[0m %s\n' "$1"; }
bad() { printf '\e[1;37;41m FALLA \e[0m %s\n' "$1"; }

printf '\e[1m%s\e[0m   %s   %s\n' "$(hostname)" "$(date '+%Y-%m-%d %H:%M')" "$(uptime -p)"
printf 'IP %s   carga %s   memoria %s\n\n' "$(hostname -I | cut -d' ' -f1)" "$(cut -d' ' -f1-3 /proc/loadavg)" \
  "$(free -h | awk '/^Mem/ {print $3 " de " $2}')"

echo 'Servicios'
for unit in agrostma-django agrostma-next nginx cloudflared redis-server ssh; do
  systemctl is-active -q "$unit" && ok "$unit" || bad "$unit"
done
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 http://localhost/)
[ "$code" = 200 ] && ok "sitio interno (HTTP $code)" || bad "sitio interno (HTTP $code)"

echo; echo 'Carpetas compartidas (servercompac)'
for dir in /mnt/compartidos /mnt/auto; do
  timeout 10 ls "$dir" >/dev/null 2>&1 && ok "$dir" || bad "$dir"
done

echo; echo 'Tareas programadas (última ejecución)'
for unit in agrostma-corte-export agrostma-fleet-daily agrostma-fleet-monthly; do
  result=$(systemctl show -P Result "$unit.service")
  last=$(systemctl show -P LastTriggerUSec "$unit.timer")
  [ "$result" = success ] && ok "$unit  ${last:-nunca}" || bad "$unit  $result  ${last:-nunca}"
done

echo; echo 'Disco'
df -h --output=target,size,used,avail,pcent / | sed 's/^/  /'

failed=$(systemctl --failed --no-legend --plain | awk '{print $1}')
[ -n "$failed" ] && { echo; echo 'Unidades con falla:'; echo "$failed" | sed 's/^/  /'; }
exit 0
