#!/usr/bin/env bash
# Tre lägen:
#   1. Argument givna -> run.py med dem, en gång (t.ex. 'retag' eller 'retag --apply')
#   2. RUN_ONCE=true  -> 'hamta' en gång
#   3. annars         -> 'schema', kör 'hamta' enligt CRON_SCHEDULE
#                        (först 'retag' om RETAG_ON_START är satt)
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
# Övertagande av en mapp med gamla filer, styrt via env så att dockyard kan
# växla läge med PATCH: dry = torrkörning i loggen, apply = skarp omtaggning.
# Båda är ofarliga att låta stå kvar, men hämtar flödet vid varje start.
case "${RETAG_ON_START:-}" in
    dry)   gosu "$PUID:$PGID" python run.py retag || true ;;
    apply) gosu "$PUID:$PGID" python run.py retag --apply || true ;;
    "")    ;;
    *)     echo "[entrypoint] Okänt RETAG_ON_START=$RETAG_ON_START, ignoreras" ;;
esac
exec gosu "$PUID:$PGID" python run.py schema
