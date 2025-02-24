#!/bin/bash

CRON_SCHEDULE="${CRON_SCHEDULE:-'0 4 * * *'}"

echo "Using CRON_SCHEDULE: $CRON_SCHEDULE"

echo "$CRON_SCHEDULE python /app/main.py >> /var/log/cron.log 2>&1" > /etc/cron.d/mycron

chmod 0644 /etc/cron.d/mycron
crontab /etc/cron.d/mycron

if [ "$RUN_IMMEDIATELY" = "true" ]; then
    echo "Running script immediately..."
    python /app/main.py
fi

cron -f
