#!/bin/sh

# Ensure the correct working directory
cd /app || exit 1

CRON_SCHEDULE="${CRON_SCHEDULE:-'0 4 * * *'}"

echo "Using CRON_SCHEDULE: $CRON_SCHEDULE"

touch /var/log/cron.log
chmod 666 /var/log/cron.log

# Set the cron job
echo "PATH=/usr/local/bin:/usr/bin:/bin" > /etc/cron.d/mycron
echo "$CRON_SCHEDULE root cd /app && /usr/local/bin/python -u main.py >> /var/log/cron.log 2>&1" > /etc/cron.d/mycron

# Set permissions and apply cron job
chmod 0644 /etc/cron.d/mycron
crontab /etc/cron.d/mycron

# Run the script immediately if required
if [ "$RUN_IMMEDIATELY" = "true" ]; then
    echo "Running script immediately..."
    cd /app && /usr/local/bin/python -u main.py >> /var/log/cron.log 2>&1
fi

# Start cron in the foreground
cron -L 15 -f
