#!/usr/bin/env python3
"""Report API mutation routes that lack any reference in backend tests or e2e smoke.

Usage (stack running for live audit optional):
  python3 scripts/api_route_audit.py
  API_URL=http://localhost:8000 python3 scripts/api_route_audit.py --live
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def load_openapi() -> dict:
    url = f"{API_URL}/openapi.json"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def collect_test_corpus() -> str:
    parts: list[str] = []
    for path in (ROOT / "backend" / "tests").glob("test_*.py"):
        parts.append(path.read_text(encoding="utf-8"))
    smoke = ROOT / "scripts" / "e2e_smoke.py"
    if smoke.is_file():
        parts.append(smoke.read_text(encoding="utf-8"))
    return "\n".join(parts)


def route_key(method: str, path: str) -> str:
    """Normalise FastAPI paths to a grep-friendly fragment."""
    frag = re.sub(r"\{[^}]+\}", "", path)
    frag = frag.strip("/")
    return f"{method} /{frag}" if frag else method


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch OpenAPI from a running API (default: parse app offline)",
    )
    args = parser.parse_args()

    if args.live:
        try:
            spec = load_openapi()
        except OSError as exc:
            print(f"Could not fetch OpenAPI from {API_URL}: {exc}", file=sys.stderr)
            return 1
    else:
        sys.path.insert(0, str(ROOT / "backend"))
        sys.path.insert(0, str(ROOT / "packages" / "domain"))
        os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
        os.environ.setdefault("AUTO_CREATE_TABLES", "false")
        os.environ.setdefault("JWT_SECRET", "audit-secret")
        from app.main import app  # noqa: WPS433

        spec = app.openapi()

    corpus = collect_test_corpus()
    uncovered: list[str] = []
    covered: list[str] = []

    for path, methods in spec.get("paths", {}).items():
        for method, meta in methods.items():
            if method.upper() not in MUTATION_METHODS:
                continue
            m = method.upper()
            key = route_key(m, path)
            # Match path segments in tests (ignore path params).
            needle = path.replace("{", "").replace("}", "")
            if needle in corpus or path in corpus:
                covered.append(key)
            else:
                uncovered.append(key)

    print(f"Mutation routes: {len(covered) + len(uncovered)}")
    print(f"Covered in tests/smoke: {len(covered)}")
    print(f"Uncovered: {len(uncovered)}")
    if uncovered:
        print("\nUncovered mutation routes (add backend or e2e tests):")
        for line in sorted(uncovered):
            print(f"  - {line}")
        return 1
    print("\nAll mutation routes referenced in tests or e2e smoke.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
