# TAFEtabler Web

Multi-tenant web version of [TAFEtabler](https://github.com/T0mDrummond86/timetabler) (desktop). The desktop app remains the reference UI; this repo reuses its **Python domain layer** behind a FastAPI API and React frontend.

## Stack

| Layer | Technology |
|-------|------------|
| Domain | Ported `timetable/core`, `timetable/solver`, `timetable/io` (no Qt) |
| API | FastAPI, SQLAlchemy, Alembic, PostgreSQL |
| Jobs | Redis (reserved for future background jobs) |
| UI | React 18, TypeScript, Vite, TanStack Query |

## Phase 1 API (auth + sessions)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create user, org, default session |
| POST | `/auth/login` | JWT (optional `organization_id`) |
| GET | `/auth/me` | Current user |
| GET | `/orgs` | Organizations you belong to |
| POST | `/orgs` | Create organization |
| GET | `/orgs/{id}/sessions` | List timetable sessions |
| POST | `/orgs/{id}/sessions` | Create session (seeds semester/week) |
| GET | `/sessions/{id}` | Session metadata |

Frontend: `/register`, `/login`, `/dashboard` (session list).

Run tests: `cd backend && pytest tests/`

## Phase 3 API (edit, move, undo)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions/{id}/staff` | Staff list (for edit dialog) |
| GET | `/sessions/{id}/rooms` | Rooms list |
| PATCH | `/sessions/{id}/bookings/{booking_id}` | Move (`day` + `start_slot`) or edit fields |
| POST | `/sessions/{id}/bookings/restore` | Undo/redo via snapshot restore |

Frontend: drag-to-move, double-click edit dialog, undo/redo toolbar (⌘Z / ⌘⇧Z).

## Phase 4 API (import, holding area, create/delete)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions/{id}/import` | Restore from desktop Timetable Export / Admin export (.xlsm) |
| GET | `/sessions/{id}/export/json` | Download session backup JSON |
| POST | `/sessions/{id}/import/json` | Restore from JSON backup |
| GET | `/sessions/{id}/holding-area?course_id=` | Unscheduled classes for course |
| POST | `/sessions/{id}/bookings` | Place class from holding area |
| DELETE | `/sessions/{id}/bookings/{id}?course_id=` | Remove booking (returns to holding) |
| GET | `/sessions/{id}/units`, `/qualifications` | Entity lists |

Frontend: Import/Export toolbar, holding area strip, drag class onto grid.

## Phase 5 API (staff/room views, entity editors)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions/{id}/timetable?view=course&course_id=` | Course week grid (default) |
| GET | `/sessions/{id}/timetable?view=staff&staff_id=` | Staff week grid |
| GET | `/sessions/{id}/timetable?view=room&day=` | Single-day room columns grid |
| PATCH | `/sessions/{id}/staff/{staff_id}` | Edit staff fields |
| PATCH | `/sessions/{id}/rooms/{room_id}` | Edit room fields |
| PATCH | `/sessions/{id}/units/{unit_id}` | Edit unit fields |
| PATCH | `/sessions/{id}/courses/{course_id}` | Edit course fields |
| PATCH | `/sessions/{id}/qualifications/{qualification_id}` | Edit qualification fields |

Frontend: Course / Staff / Room view switcher, day picker for room view, entity editors panel.

## Phase 6 API (change log — no auto-solve)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions/{id}/change-log?resolved=` | Full or resolved timetabling change log |
| PATCH | `/sessions/{id}/change-log/entries/{entry_id}/notes` | Save note on resolved row |
| POST | `/sessions/{id}/change-log/rollback` | Roll booking back to earliest logged state |
| GET | `/sessions/{id}/change-log/export?resolved=true` | Download resolved change log `.xlsx` |

Frontend: Change log panel (full / resolved modes, notes, rollback, Excel export).

---

## Quick start (Docker)

```bash
cd timetabler-web
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 — docs at `/docs`, health at `/health`
- Frontend: http://localhost:5173

## Local development (without Docker)

**Domain + API**

```bash
cd packages/domain && python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install -r ../../backend/requirements.txt

# Postgres + Redis running locally (see .env.example)
cd ../../backend
uvicorn app.main:app --reload --app-dir . --env-file ../.env
```

Set `PYTHONPATH` to `packages/domain` if not using editable install.

**Frontend**

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

## Repo layout

```
packages/domain/     # timetabler-domain pip package (from desktop)
backend/app/         # FastAPI application
frontend/            # React SPA
docker-compose.yml
scripts/             # sync-domain-from-desktop.sh
```

## Roadmap

| Phase | Scope | Status |
|-------|--------|--------|
| **0** | Repo bootstrap, domain copy, health API, React shell | Done |
| **1** | Auth, orgs, sessions, `timetable_session_id` on domain tables | Done |
| **2** | Read-only week grid (course view) | Done |
| **3** | Booking edit, move, undo | Done |
| **4** | Desktop import, holding area, create/delete bookings | Done |
| **5** | Staff/room/class editors, multi-view grids (staff, room) | Done |
| **6** | Change log UI (full / resolved, notes, rollback, export) | Done |
| **7** | Block delivery, semester views, Excel export v2, print | Next |

## Syncing from desktop

After changes land in `timetabler` (desktop):

```bash
./scripts/sync-domain-from-desktop.sh
```

Re-apply web-only patches under `packages/domain/timetable/io/` (`export_headers.py`, changelog/violations imports) if those files were overwritten.

## License

Same as the desktop project (private / institutional use unless otherwise noted).
