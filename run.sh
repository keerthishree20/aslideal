#!/usr/bin/env bash
# Sets up the backend once, then serves the app on http://localhost:8000.
# With no SERPAPI_KEY in .env it runs in demo mode on the recorded responses.
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  # FastAPI needs Python 3.9 or newer; use the newest one installed.
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then PY=$c; break; fi
  done
  [ -n "$PY" ] || { echo "Needs Python 3.9 or newer." >&2; exit 1; }
  "$PY" -m venv .venv
  .venv/bin/pip install -q -r requirements-dev.txt
fi
exec .venv/bin/uvicorn aslideal.api:app --port "${PORT:-8000}"
