# Timetabler Web

Multi-tenant web reimplementation of [Joondalup Timetable](https://github.com/T0mDrummond86/timetabler) (desktop). The desktop app remains the reference UI; this repo reuses its **Python domain layer** behind a FastAPI API and React frontend.

## Stack

| Layer | Technology |
|-------|------------|
| Domain | Ported `timetable/core`, `timetable/solver`, `timetable/io` (no Qt) |
| API | FastAPI, SQLAlchemy, Alembic, PostgreSQL |
| Jobs | Redis + RQ (solver worker — Phase 5) |
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

Run tests: `cd backend && pytest tests/test_phase1_auth.py tests/test_phase2_timetable.py`

## Phase 2 API (read-only grid)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions/{id}/courses` | Courses in session |
| GET | `/sessions/{id}/timetable?course_id=` | Week grid payload (bookings, colours, violations) |
| POST | `/sessions/{id}/seed-demo` | Sample course + bookings (empty sessions only) |

Frontend: `/timetable/:sessionId` — course picker, coloured week grid, violations strip.

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
| **3** | Booking edit, move, undo | Next |
| **4** | Staff / rooms / classes editors, JSON import/export |
| **5** | Async solver, change log |
| **6** | Holding area, split views, print, Excel exports |

## Syncing from desktop

After changes land in `timetabler` (desktop):

```bash
./scripts/sync-domain-from-desktop.sh
```

Re-apply web-only patches under `packages/domain/timetable/io/` (`export_headers.py`, changelog/violations imports) if those files were overwritten.

## License

Same as the desktop project (private / institutional use unless otherwise noted).
