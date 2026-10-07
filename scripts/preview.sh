#!/usr/bin/env bash
# Temporary public URL. Keep both this process and scripts/start.sh running.
set -euo pipefail
cd "$(dirname "$0")/.."
provider="${1:-cloudflare}"
port="${PORT:-8000}"
.venv/bin/python - "$port" <<'PY'
import sys, urllib.request
port = int(sys.argv[1])
assert 1 <= port <= 65535
with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
    assert response.status == 200
PY
case "$provider" in
  cloudflare)
    tunnel_binary="${CLOUDFLARED_BIN:-cloudflared}"
    if ! command -v "$tunnel_binary" >/dev/null; then
      echo "Install cloudflared from https://developers.cloudflare.com/tunnel/downloads/" >&2
      exit 1
    fi
    exec "$tunnel_binary" tunnel --url "http://127.0.0.1:$port" --protocol http2 --no-autoupdate
    ;;
  ngrok)
    if ! command -v ngrok >/dev/null; then
      echo "Install ngrok from https://ngrok.com/download; configure its account securely." >&2
      exit 1
    fi
    # ngrok uses its normal config or NGROK_AUTHTOKEN, and supports http_proxy.
    # Never echo the token or pass it as a command-line argument.
    exec ngrok http "http://127.0.0.1:$port"
    ;;
  *) echo "Usage: $0 [cloudflare|ngrok]" >&2; exit 2 ;;
esac
