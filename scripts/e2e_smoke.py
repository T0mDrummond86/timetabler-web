#!/usr/bin/env python3
"""Live end-to-end smoke test against a running TAFEtabler stack.

Usage:
  API_URL=http://localhost:8000 FRONTEND_URL=http://localhost:5173 python3 scripts/e2e_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")

PASS = 0
FAIL = 0


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✓ {name}")


def fail(name: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    msg = f"  ✗ {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    params: dict | None = None,
    expect: int | tuple[int, ...] = 200,
) -> tuple[int, dict | list | str | bytes | None]:
    url = f"{API_URL}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read()
            resp_ct = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read()
        resp_ct = e.headers.get("Content-Type", "")
    except urllib.error.URLError as e:
        raise RuntimeError(f"{method} {url}: {e}") from e

    expected = (expect,) if isinstance(expect, int) else expect
    if status not in expected:
        snippet = raw[:300].decode(errors="replace") if raw else ""
        raise RuntimeError(f"{method} {path} → {status} (expected {expected}): {snippet}")

    if not raw:
        return status, None
    if "json" in resp_ct or raw[:1] in (b"{", b"["):
        return status, json.loads(raw.decode())
    return status, raw


def section(title: str) -> None:
    print(f"\n{title}")


def main() -> int:
    print(f"API: {API_URL}")
    print(f"Frontend: {FRONTEND_URL}")

    section("Infrastructure")
    try:
        status, health = request("GET", "/health")
        assert isinstance(health, dict)
        if health.get("status") == "ok" and health.get("database") == "up":
            ok(f"health (phase {health.get('phase')})")
        else:
            fail("health", str(health))
    except RuntimeError as e:
        fail("health", str(e))
        print("\nAborting: API not reachable.")
        return 1

    try:
        with urllib.request.urlopen(FRONTEND_URL, timeout=10) as resp:
            if resp.status == 200:
                ok("frontend reachable")
            else:
                fail("frontend reachable", f"status {resp.status}")
    except urllib.error.URLError as e:
        fail("frontend reachable", str(e))

    section("Auth & session")
    email = f"e2e-{uuid4().hex[:10]}@example.com"
    try:
        _, reg = request("POST", "/auth/register", body={
            "email": email,
            "password": "password123",
            "name": "E2E Tester",
            "organization_name": f"E2E Org {uuid4().hex[:6]}",
        }, expect=201)
        assert isinstance(reg, dict)
        token = reg["access_token"]
        ok("register")

        _, me = request("GET", "/auth/me", token=token)
        assert isinstance(me, dict) and me["email"] == email
        ok("auth/me")

        _, orgs = request("GET", "/orgs", token=token)
        org_id = orgs[0]["id"]
        ok("orgs")

        _, sessions = request("GET", f"/orgs/{org_id}/sessions", token=token)
        session_id = sessions[0]["id"]
        ok("sessions list")
    except RuntimeError as e:
        fail("auth flow", str(e))
        return 1

    headers_ctx = token
    section("Seed & entity lists")
    try:
        _, seed = request("POST", f"/sessions/{session_id}/seed-demo", token=headers_ctx)
        ok("seed-demo")

        _, courses = request("GET", f"/sessions/{session_id}/courses", token=headers_ctx)
        _, staff_list = request("GET", f"/sessions/{session_id}/staff", token=headers_ctx)
        course_id = seed.get("course_id") or courses[0]["id"]
        staff_id = staff_list[0]["id"]
        assert isinstance(courses, list) and courses
        assert isinstance(staff_list, list) and staff_list

        for path in ("courses", "staff", "rooms", "units", "qualifications"):
            _, data = request("GET", f"/sessions/{session_id}/{path}", token=headers_ctx)
            assert isinstance(data, list) and len(data) > 0
            ok(f"GET /{path} ({len(data)} rows)")
    except RuntimeError as e:
        fail("seed/entities", str(e))
        return 1

    section("Entity editors")
    qual_id = None
    try:
        quals = request("GET", f"/sessions/{session_id}/qualifications", token=headers_ctx)[1]
        assert isinstance(quals, list) and quals
        qual_id = quals[0]["id"]
        _, patched = request(
            "PATCH",
            f"/sessions/{session_id}/qualifications/{qual_id}",
            token=headers_ctx,
            body={"name": quals[0]["name"], "num_groups": quals[0].get("num_groups") or 1},
        )
        assert isinstance(patched, dict)
        ok("patch qualification")

        request(
            "GET",
            f"/sessions/{session_id}/timetable",
            token=headers_ctx,
            params={"view": "block_delivery"},
            expect=422,
        )
        ok("block_delivery rejects missing course_id")

        _, block = request(
            "POST",
            f"/sessions/{session_id}/qualifications/{qual_id}/create-block",
            token=headers_ctx,
        )
        assert isinstance(block, dict) and block.get("course_id")
        ok("create block group")

        request(
            "GET",
            f"/sessions/{session_id}/block-delivery-panel",
            token=headers_ctx,
            params={"qualification_id": qual_id, "course_id": block["course_id"]},
        )
        ok("block-delivery-panel")

        _, block_grid = request(
            "GET",
            f"/sessions/{session_id}/timetable",
            token=headers_ctx,
            params={
                "view": "block_delivery",
                "course_id": block["course_id"],
                "block_week_index": 1,
            },
        )
        assert isinstance(block_grid, dict) and block_grid.get("view") == "block_delivery"
        ok("block_delivery timetable")

        _, dup = request(
            "POST",
            f"/sessions/{session_id}/block-groups/{block['course_id']}/duplicate",
            token=headers_ctx,
            body={"new_code": f"{block['course_code']}B"},
        )
        assert isinstance(dup, dict) and dup.get("course_id")
        ok("duplicate block group")
    except RuntimeError as e:
        fail("entity editors", str(e))

    section("Timetable views")
    views: list[tuple[str, dict]] = [
        ("course", {"view": "course", "course_id": course_id}),
        ("staff", {"view": "staff", "staff_id": staff_id}),
        ("room", {"view": "room", "day": 0}),
        ("day", {"view": "day", "day": 0}),
        ("course_semester", {"view": "course_semester", "course_id": course_id, "semester_week": 1}),
        ("unassigned_lecturer", {"view": "unassigned_lecturer"}),
        ("block_overview", {}),
    ]
    for view_name, params in views:
        try:
            if view_name == "block_overview":
                _, data = request("GET", f"/sessions/{session_id}/block-overview", token=headers_ctx)
            else:
                _, ents = request(
                    "GET",
                    f"/sessions/{session_id}/timetable-entities",
                    token=headers_ctx,
                    params={"view": view_name},
                )
                assert isinstance(ents, list)
                _, data = request(
                    "GET",
                    f"/sessions/{session_id}/timetable",
                    token=headers_ctx,
                    params=params,
                )
            assert isinstance(data, dict)
            ok(f"view {view_name}")
        except RuntimeError as e:
            fail(f"view {view_name}", str(e))

    section("Auxiliary panels")
    aux: list[tuple[str, str, dict | None]] = [
        ("holding-area", f"/sessions/{session_id}/holding-area", {"kind": "course", "course_id": course_id}),
        ("change-log", f"/sessions/{session_id}/change-log", None),
        ("violations-report", f"/sessions/{session_id}/violations-report", None),
        ("class-custodians", f"/sessions/{session_id}/class-custodians", None),
        ("usage/staff", f"/sessions/{session_id}/usage/staff", None),
        ("usage/rooms", f"/sessions/{session_id}/usage/rooms", None),
        ("course-semester-schedule", f"/sessions/{session_id}/course-semester-schedule", {"course_id": course_id}),
    ]
    for name, path, params in aux:
        try:
            request("GET", path, token=headers_ctx, params=params)
            ok(name)
        except RuntimeError as e:
            fail(name, str(e))

    section("Booking mutation")
    try:
        _, grid = request(
            "GET",
            f"/sessions/{session_id}/timetable",
            token=headers_ctx,
            params={"view": "course", "course_id": course_id},
        )
        bookings = grid.get("bookings") or []
        if not bookings:
            fail("move booking", "no bookings in demo grid")
        else:
            b = bookings[0]
            bid = b["id"]
            day = b["day"]
            start = min(b["start_slot"] + 1, grid["num_slots"] - (b["end_slot"] - b["start_slot"]))
            _, mut = request(
                "PATCH",
                f"/sessions/{session_id}/bookings/{bid}",
                token=headers_ctx,
                body={"course_id": course_id, "day": day, "start_slot": start},
            )
            assert mut.get("change")
            ok("move booking")

            change = mut["change"]
            _, restored = request(
                "POST",
                f"/sessions/{session_id}/bookings/restore",
                token=headers_ctx,
                body={
                    "course_id": course_id,
                    "action": "undo",
                    "label": change["description"],
                    "snapshots": change["before"],
                },
            )
            assert isinstance(restored, dict) and restored.get("grid")
            ok("undo restore")
    except RuntimeError as e:
        fail("booking mutation", str(e))

    section("Exports (smoke)")

    def _workbook_contains_class(data: bytes, class_name: str) -> bool:
        needle = class_name.encode("utf-8")
        if needle in data:
            return True
        import io
        import zipfile

        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            blob = b"".join(
                zf.read(n) for n in zf.namelist() if n.endswith(".xml") or n.endswith(".rels")
            )
            return needle in blob
        except zipfile.BadZipFile:
            return False

    demo_class = "Cyber Foundations"
    exports = [
        ("export/json", f"/sessions/{session_id}/export/json", None),
        (
            "export/timetable",
            f"/sessions/{session_id}/export/timetable",
            {"variant": "v2"},
        ),
        ("export/admin", f"/sessions/{session_id}/export/admin", None),
        ("export/change-log", f"/sessions/{session_id}/export/change-log", None),
    ]
    for name, path, params in exports:
        try:
            status, raw = request("GET", path, token=headers_ctx, params=params)
            if isinstance(raw, dict) and raw:
                ok(name)
                continue
            if not isinstance(raw, bytes) or len(raw) < 50:
                fail(name, "empty response")
                continue
            if raw[:2] != b"PK":
                fail(name, "not a valid xlsx/xlsm zip")
                continue
            if "timetable" in name or name == "export/admin":
                if not _workbook_contains_class(raw, demo_class):
                    fail(name, f"missing class name {demo_class!r}")
                    continue
            ok(name)
        except RuntimeError as e:
            fail(name, str(e))

    section("Summary")
    total = PASS + FAIL
    print(f"\n{PASS}/{total} checks passed")
    if FAIL:
        print(f"{FAIL} failed")
        return 1
    print("All end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
