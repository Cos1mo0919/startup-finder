#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
export npm_config_cache="${npm_config_cache:-/workspace/.cache/npm}"
uv sync --frozen
npm ci --prefix frontend --no-audit --no-fund
npm run build --prefix frontend
