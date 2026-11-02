#!/usr/bin/env bash
# Vigia externo do LiveSafe — executado pelo livesafe-watchdog.timer a cada 30 s.
#
# O systemd já religa o serviço quando ele CAI. Este script cobre o caso em que
# ele TRAVA: o processo continua vivo, mas não responde. Se /healthz falhar 3
# vezes seguidas (com 5 s entre elas), o serviço é reiniciado.
set -u

CONF="${LIVESAFE_CONFIG:-/etc/livesafe/config.json}"
PORT=$(node -p "try{require('$CONF').http.port||8080}catch(e){8080}" 2>/dev/null || echo 8080)
URL="http://127.0.0.1:${PORT}/healthz"
TRIES=3

# Só age se o serviço deveria estar rodando: parado à mão ou ainda subindo, não mexe.
[[ "$(systemctl is-active livesafe)" == "active" ]] || exit 0
STARTED=$(systemctl show livesafe -p ActiveEnterTimestampMonotonic --value)
NOW=$(awk '{printf "%d", $1 * 1000000}' /proc/uptime)
if [[ -n "$STARTED" && "$STARTED" != "0" ]] && (( NOW - STARTED < 60000000 )); then
  exit 0 # menos de 60 s no ar: dá tempo de inicializar
fi

for ((i = 1; i <= TRIES; i++)); do
  if curl -fsS -m 5 -o /dev/null "$URL"; then
    exit 0
  fi
  (( i < TRIES )) && sleep 5
done

logger -t livesafe-watchdog -p daemon.warning "LiveSafe não respondeu em $URL após $TRIES tentativas; reiniciando o serviço"
systemctl restart livesafe
