#!/bin/sh

# Ensure the correct working directory
cd /app || exit 1

CRON_SCHEDULE="${CRON_SCHEDULE:-'0 4 * * *'}"

echo "Using CRON_SCHEDULE: $CRON_SCHEDULE"

# Set the cron job
echo "$CRON_SCHEDULE root cd /app && python main.py >> /var/log/cron.log 2>&1" > /etc/cron.d/mycron

# Set permissions and apply cron job
chmod 0644 /etc/cron.d/mycron
crontab /etc/cron.d/mycron

# Run the script immediately if required
if [ "$RUN_IMMEDIATELY" = "true" ]; then
    echo "Running script immediately..."
    cd /app && python main.py
fi

# Start cron in the foreground
cron -f
