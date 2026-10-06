#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/ruff check backend tests
.venv/bin/pytest -q
npm run build --prefix frontend
npm run test:e2e --prefix frontend
