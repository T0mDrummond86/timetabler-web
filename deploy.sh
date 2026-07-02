#!/usr/bin/env bash
set -euo pipefail

# One-command deploy of timetabler-web to the production VM.
# Pushes the local working copy via rsync, then rebuilds/restarts the
# Docker stack on the VM. Migrations run automatically on API start.
#
# Usage:  ./deploy.sh
# The Docker build log is hidden by default (only the final status shows).
# To stream the full build output, run:  VERBOSE=1 ./deploy.sh
# Override target with env vars if needed:
#   DEPLOY_TARGET=localadmin@host DEPLOY_DIR='~/timetabler-web' ./deploy.sh

VM="${DEPLOY_TARGET:-localadmin@timetabler.rbfe.com.au}"
REMOTE_DIR="${DEPLOY_DIR:-~/timetabler-web}"
HEALTH_URL="${HEALTH_URL:-https://timetabler.rbfe.com.au/api/health}"
VERBOSE="${VERBOSE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Syncing code to ${VM}:${REMOTE_DIR}"
rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  --exclude 'frontend/dist' \
  --exclude '.env' \
  --exclude '.env.prod' \
  --exclude 'backups' \
  --exclude '.DS_Store' \
  ./ "${VM}:${REMOTE_DIR}/"

echo "==> Building and restarting the stack"
BUILD_CMD="cd ${REMOTE_DIR} && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build"
if [ "$VERBOSE" = "1" ]; then
  ssh "$VM" "$BUILD_CMD"
else
  # Quiet by default: capture the (noisy) build log and only surface it on failure.
  BUILD_LOG="$(mktemp -t timetabler-deploy.XXXXXX)"
  if ssh "$VM" "$BUILD_CMD" >"$BUILD_LOG" 2>&1; then
    echo "    Build complete (run VERBOSE=1 ./deploy.sh to stream build output)"
    rm -f "$BUILD_LOG"
  else
    echo "!! Build/restart failed — last 40 lines:" >&2
    tail -n 40 "$BUILD_LOG" >&2
    echo "   Full log kept at: $BUILD_LOG" >&2
    exit 1
  fi
fi

echo "==> Waiting for API health"
sleep 8
if curl -fsS --max-time 25 "$HEALTH_URL" >/dev/null; then
  echo "==> Healthy. Deployed: ${HEALTH_URL%/api/health}"
else
  echo "!! Health check failed at ${HEALTH_URL}" >&2
  echo "   Check logs: ssh ${VM} 'cd ${REMOTE_DIR} && docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=50 api'" >&2
  exit 1
fi
