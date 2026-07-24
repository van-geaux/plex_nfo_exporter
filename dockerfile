FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app
RUN chmod 777 /app

COPY main.py .
COPY requirements.txt .

RUN mkdir -p logs

RUN pip install --no-cache-dir -r requirements.txt

ADD https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64 /tmp/supercronic
RUN echo "87625cd179eff21226f0be6f2f47dd357037064598e6c1f9ffcbd0335d402bbd  /tmp/supercronic" | sha256sum -c - \
    && install -m 0755 /tmp/supercronic /usr/local/bin/supercronic \
    && rm /tmp/supercronic

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
