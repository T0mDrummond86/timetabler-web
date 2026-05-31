#!/usr/bin/env bash
# Run API locally without Docker (requires Postgres on localhost:5432).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP_VENV="${DESKTOP_VENV:-$ROOT/../timetable/.venv}"
export PYTHONPATH="$ROOT/packages/domain:$ROOT/backend"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://timetabler:timetabler@localhost:5432/timetabler}"
cd "$ROOT/backend"
exec "$DESKTOP_VENV/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port 8000
