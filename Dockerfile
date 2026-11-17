# Shadowfolio in one image: the backend, serving the API, the MCP server and the built web app on one origin.
# Configuration comes from the environment at run time (see docker-compose.yml and .env.example), never from the image.

# The web app, built once with Node; only its static files go into the image.
FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so code changes reuse their layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web
# Readable by the app's user whatever the permissions in the checkout (COPY keeps them).
RUN chmod -R a+rX /app/src /app/web

# A user of its own, owning the data volume.
RUN useradd --system --create-home shadowfolio && mkdir /data && chown shadowfolio /data
USER shadowfolio
ENV PATH="/app/.venv/bin:$PATH" \
    SHADOWFOLIO_ENV=local \
    SHADOWFOLIO_HOST=0.0.0.0 \
    SHADOWFOLIO_PORT=8000 \
    SHADOWFOLIO_DB=/data/shadowfolio.db \
    SHADOWFOLIO_WEB_DIR=/app/web
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/auth/config', timeout=4)"
CMD ["shadowfolio"]
