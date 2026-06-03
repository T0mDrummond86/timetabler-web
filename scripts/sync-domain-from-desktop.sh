#!/usr/bin/env bash
# Copy domain logic from the desktop timetabler repo into packages/domain.
set -euo pipefail

DESKTOP_ROOT="${DESKTOP_ROOT:-$(cd "$(dirname "$0")/../../timetable" && pwd)}"
WEB_DOMAIN="$(cd "$(dirname "$0")/../packages/domain/timetable" && pwd)"

if [[ ! -d "$DESKTOP_ROOT/timetable/core" ]]; then
  echo "Desktop repo not found at $DESKTOP_ROOT" >&2
  exit 1
fi

echo "Syncing from $DESKTOP_ROOT -> $WEB_DOMAIN"

rsync -a --delete --exclude='__pycache__' \
  "$DESKTOP_ROOT/timetable/constants.py" \
  "$WEB_DOMAIN/../" 2>/dev/null || cp "$DESKTOP_ROOT/timetable/constants.py" "$WEB_DOMAIN/../timetable/" 2>/dev/null || true

mkdir -p "$WEB_DOMAIN/core" "$WEB_DOMAIN/solver" "$WEB_DOMAIN/io"
rsync -a --delete --exclude='__pycache__' \
  "$DESKTOP_ROOT/timetable/core/" "$WEB_DOMAIN/core/"
rsync -a --delete --exclude='__pycache__' \
  "$DESKTOP_ROOT/timetable/solver/" "$WEB_DOMAIN/solver/"
rsync -a --delete --exclude='__pycache__' \
  "$DESKTOP_ROOT/timetable/io/" "$WEB_DOMAIN/io/"

mkdir -p "$(dirname "$WEB_DOMAIN")/templates"
rsync -a \
  "$DESKTOP_ROOT/templates/admin_export_base.xlsx" \
  "$(dirname "$WEB_DOMAIN")/templates/"
cp "$DESKTOP_ROOT/adminExportStyleGuide.xlsx" "$(dirname "$WEB_DOMAIN")/"

# Re-apply web-only patches
if [[ -f "$(dirname "$0")/patches/io-export-headers.py" ]]; then
  cp "$(dirname "$0")/patches/io-export-headers.py" "$WEB_DOMAIN/io/export_headers.py"
fi

echo "Done. Re-apply io/changelog_export.py and io/violations_export.py patches if needed."
