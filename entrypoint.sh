#!/bin/sh

# Ensure the correct working directory
cd /app || exit 1

CRON_SCHEDULE="${CRON_SCHEDULE:-'0 4 * * *'}"

echo "Using CRON_SCHEDULE: $CRON_SCHEDULE"

# Set the cron job
echo "PATH=/usr/local/bin:/usr/bin:/bin" > /etc/cron.d/mycron
# Redirect cron job output to stdout/stderr instead of a file
echo "$CRON_SCHEDULE root cd /app && /usr/local/bin/python -u main.py >> /proc/1/fd/1 2>> /proc/1/fd/2" >> /etc/cron.d/mycron

# Set permissions and apply cron job
chmod 0644 /etc/cron.d/mycron
crontab /etc/cron.d/mycron

# Run the script immediately if required
if [ "$RUN_IMMEDIATELY" = "true" ]; then
    echo "Running script immediately..."
    cd /app && /usr/local/bin/python -u main.py >> /proc/1/fd/1 2>> /proc/1/fd/2
fi

# Start cron and forward its output to stdout/stderr
cron -L 15 -f