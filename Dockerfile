# Pinned to the nginx stable line. Dependabot proposes updates to this tag.
FROM nginx:1.30-alpine

LABEL org.opencontainers.image.title="Outpost"
LABEL org.opencontainers.image.description="Outpost is a weather web dashboard"
# The release workflow adds the version and other labels when it publishes the image.

RUN apk add --no-cache python3 py3-pip bash curl tzdata

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /app/requirements.txt

COPY web/ /usr/share/nginx/html/
COPY assets/ /usr/share/nginx/html/assets/
COPY app/ /app/
COPY VERSION /app/VERSION

# nginx serves weather.json from the persistent /data volume
RUN mkdir -p /data \
    && ln -sfn /data /usr/share/nginx/html/data \
    && chmod +x /app/start.sh

# Never let browsers cache the weather JSON
RUN printf 'server {\n  listen 80;\n  root /usr/share/nginx/html;\n  index index.html;\n  location /data/ {\n    add_header Cache-Control "no-store";\n  }\n}\n' > /etc/nginx/conf.d/default.conf

VOLUME /data
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 /app/outpost_health.py || exit 1

CMD ["/app/start.sh"]
