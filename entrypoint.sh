#!/bin/sh

cd /app || exit 1

CRON_SCHEDULE="${CRON_SCHEDULE:-'0 4 * * *'}"

echo "Using CRON_SCHEDULE: $CRON_SCHEDULE"

echo "PATH=/usr/local/bin:/usr/bin:/bin" > /etc/cron.d/mycron
echo "$CRON_SCHEDULE root cd /app && /usr/local/bin/python -u main.py >> /proc/1/fd/1 2>> /proc/1/fd/2" >> /etc/cron.d/mycron

chmod 0644 /etc/cron.d/mycron
crontab /etc/cron.d/mycron

if [ "$RUN_IMMEDIATELY" = "true" ]; then
    echo "Running script immediately..."
    cd /app && /usr/local/bin/python -u main.py >> /proc/1/fd/1 2>> /proc/1/fd/2
fi

cron -L 15 -f