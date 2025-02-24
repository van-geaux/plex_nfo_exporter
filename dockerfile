FROM python:3.11-slim

WORKDIR /app

COPY main.py .
COPY requirements.txt .

RUN mkdir -p logs

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
