#!/usr/bin/env bash
# Full end-to-end verification: backend tests, frontend build, live smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Backend unit/integration tests (Docker) ==="
docker compose run --rm --no-deps \
  -v "$ROOT/backend:/work/backend" \
  -w /work \
  -e DATABASE_URL=sqlite+pysqlite:///:memory: \
  -e AUTO_CREATE_TABLES=false \
  -e JWT_SECRET=test-secret \
  -e PYTHONPATH=/app/packages/domain:/work/backend \
  api pytest backend/tests/ -v

echo ""
echo "=== Frontend production build (Docker Node) ==="
docker run --rm \
  -v "$ROOT/frontend:/app" \
  -w /app \
  node:22-alpine \
  sh -c "npm install && npm run build"

echo ""
echo "=== Live stack smoke test ==="
if ! curl -sf "${API_URL:-http://localhost:8000}/health" >/dev/null 2>&1; then
  echo "API not reachable at ${API_URL:-http://localhost:8000}. Start the stack first:"
  echo "  docker compose up --build"
  exit 1
fi

python3 "$ROOT/scripts/e2e_smoke.py"

echo ""
echo "=== API mutation route audit ==="
python3 "$ROOT/scripts/api_route_audit.py" || true

echo ""
echo "All end-to-end checks completed successfully."
