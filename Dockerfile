# Pinned to the nginx stable line. Dependabot proposes updates to this tag.
FROM nginx:1.31-alpine

LABEL org.opencontainers.image.title="Outpost"
LABEL org.opencontainers.image.description="Outpost is a weather web dashboard"
# The release workflow adds the version and other labels when it publishes the image.

# Outpost uses only Python's standard library, so there are no pip packages to install.
# (bash runs start.sh, and tzdata makes the TZ setting work.)
RUN apk add --no-cache python3 bash tzdata

WORKDIR /app

COPY web/ /usr/share/nginx/html/
COPY assets/ /usr/share/nginx/html/assets/
COPY app/ /app/
COPY VERSION /app/VERSION

# nginx serves weather.json from the persistent /data volume.
# /config/themes is where people mount their own themes (empty unless something is mounted there).
RUN mkdir -p /data /config/themes \
    && ln -sfn /data /usr/share/nginx/html/data \
    && chmod +x /app/start.sh

COPY nginx/default.conf /etc/nginx/conf.d/default.conf

VOLUME /data
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 /app/outpost_health.py || exit 1

CMD ["/app/start.sh"]
