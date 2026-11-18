FROM python:3.12-slim

# gosu: kör som PUID/PGID (Unraid: 99/100). tzdata: TZ för schema och datum.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY hamtare/ ./hamtare/
COPY app/ ./app/
COPY run.py config.yaml entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENV TZ=Europe/Stockholm \
    PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/state/config.yaml \
    STATE_DIR=/state \
    CRON_SCHEDULE="30 */3 * * *" \
    WEBUI_PORT=8000

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
