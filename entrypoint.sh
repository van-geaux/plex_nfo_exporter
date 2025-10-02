#!/bin/sh

cd /app || exit 1

CRON_SCHEDULE="${CRON_SCHEDULE:-0 4 * * *}"

echo "Using CRON_SCHEDULE: $CRON_SCHEDULE"

{
  echo "PATH=/usr/local/bin:/usr/bin:/bin"
  echo "$CRON_SCHEDULE python /app/main.py"
} > /app/crontab

if [ "$RUN_IMMEDIATELY" = "true" ]; then
    echo "Running script immediately..."
    python /app/main.py
fi

exec supercronic /app/crontab
