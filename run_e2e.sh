#!/usr/bin/env bash
# Browser end-to-end tests. One-time setup: .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium
cd "$(dirname "$0")"
PY="${PY:-../.venv/bin/python}"; [ -x "$PY" ] || PY=python3
exec "$PY" -m pytest tests/e2e -q -p no:cacheprovider "$@"
