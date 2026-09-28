#!/usr/bin/env bash
# Start Davish's House locally. Usage: ./run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-../.venv/bin/python}"
[ -x "$PY" ] || PY=python3
[ -f davish.db ] || "$PY" seed.py
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${1:-8000}" --reload
