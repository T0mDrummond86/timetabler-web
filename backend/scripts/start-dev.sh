#!/bin/sh
set -e

if [ -f /app/backend/alembic.ini ]; then
  cd /app/backend
  alembic upgrade head
  cd /app
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
