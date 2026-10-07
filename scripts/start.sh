#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/uvicorn || ! -f frontend/dist/index.html ]]; then
  echo "Dependencies or frontend build missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi
exec .venv/bin/uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
