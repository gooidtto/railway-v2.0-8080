# syntax=docker/dockerfile:1
ARG XRAY_VERSION=26.3.27
FROM ghcr.io/xtls/xray-core:${XRAY_VERSION}@sha256:592ec4d11f656db95598d01e76dbcc6e002d67360b96a5436500a938230f52c7 AS xray
FROM python:3.12-alpine3.22
ARG XRAY_VERSION
ENV XRAY_VERSION=${XRAY_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    GATEWAY_PORT=8080 \
    XRAY_HTTP_PORT=10086 \
    XRAY_PORT=10087 \
    XRAY_CONFIG=/etc/xray/config.json \
    XRAY_READY_FILE=/data/.xray-ready \
    DATA_DIR=/data \
    XRAY_LOGLEVEL=warning \
    XHTTP_PATH=/xhttp \
    XHTTP_MODE=auto \
    REALITY_TARGET=www.cloudflare.com:443 \
    REALITY_SNI=www.cloudflare.com \
    REALITY_FINGERPRINT=chrome \
    GRPC_SERVICE_NAME=grpc-service \
    WS_PATH=/ws \
    SUBSCRIPTION_FILE=/data/subscription.txt \
    SUBSCRIPTION_TOKEN_FILE=/data/subscription_token.txt
RUN mkdir -p /etc/xray /data /opt/xray/scripts /opt/xray/site /data/ws
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY scripts/ /opt/xray/scripts/
COPY site/ /opt/xray/site/
RUN chmod 0755 /usr/local/bin/xray /opt/xray/scripts/*.sh /opt/xray/scripts/*.py && chmod 0644 /opt/xray/site/*
EXPOSE 8080 10086 10087 10088 10089
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=3).read()"
WORKDIR /opt/xray
ENTRYPOINT ["/opt/xray/scripts/start.sh"]
