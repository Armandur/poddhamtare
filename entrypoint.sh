#!/usr/bin/env bash
# Tre lägen:
#   1. Argument givna -> run.py med dem, en gång (t.ex. 'retag' eller 'retag --apply')
#   2. RUN_ONCE=true  -> 'hamta' en gång
#   3. annars         -> 'schema', kör 'hamta' enligt CRON_SCHEDULE
set -euo pipefail

PUID="${PUID:-99}"
PGID="${PGID:-100}"

mkdir -p /state
if [ ! -f "$CONFIG_PATH" ]; then
    echo "[entrypoint] Ingen $CONFIG_PATH, kopierar standardkonfigen"
    cp /app/config.yaml "$CONFIG_PATH"
fi
chown -R "$PUID:$PGID" /state 2>/dev/null || true

if [ "$#" -gt 0 ]; then
    exec gosu "$PUID:$PGID" python run.py "$@"
fi
if [ "${RUN_ONCE:-false}" = "true" ]; then
    exec gosu "$PUID:$PGID" python run.py hamta
fi
exec gosu "$PUID:$PGID" python run.py schema
