#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"
export npm_config_cache="${npm_config_cache:-${XDG_CACHE_HOME:-$HOME/.cache}/npm}"
uv sync --frozen
npm ci --prefix frontend --no-audit --no-fund
npm run build --prefix frontend

# Create/migrate the database and import missing sources; no collection or deletion.
.venv/bin/python -m backend.app.cli --seed-sources
