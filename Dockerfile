FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN --mount=type=secret,id=build_ca,target=/run/secrets/build_ca \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
RUN --mount=type=secret,id=build_ca,target=/run/secrets/build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; pip install --no-cache-dir uv==0.12.19
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca,target=/run/secrets/build_ca \
    if [ -f /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; uv sync --frozen --no-dev
COPY backend/ backend/
COPY sources.json ./
COPY --from=frontend /build/frontend/dist frontend/dist/
RUN useradd --create-home --uid 10001 finder && mkdir -p /app/data && chown -R finder:finder /app
USER finder
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
CMD ["/app/.venv/bin/uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
