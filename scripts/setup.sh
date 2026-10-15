#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"
export npm_config_cache="${npm_config_cache:-${XDG_CACHE_HOME:-$HOME/.cache}/npm}"
uv sync --frozen
npm ci --prefix frontend --no-audit --no-fund
npm run build --prefix frontend

# Database creation is deliberate: run the migration script before starting the
# application against a new PostgreSQL database. Setup never writes live data.
