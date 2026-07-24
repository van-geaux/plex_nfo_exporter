FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app
RUN chmod 777 /app

COPY main.py .
COPY requirements.txt .

RUN mkdir -p logs

RUN pip install --no-cache-dir -r requirements.txt

ADD https://github.com/aptible/supercronic/releases/download/v0.2.48/supercronic-linux-amd64 /tmp/supercronic
RUN echo "88c1b66b94c486f972fdd1a4d1f901e3e75ff04f749cddd60c5db573e3a33c6c  /tmp/supercronic" | sha256sum -c - \
    && install -m 0755 /tmp/supercronic /usr/local/bin/supercronic \
    && rm /tmp/supercronic

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
