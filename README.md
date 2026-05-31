# Timetabler Web

Multi-tenant web reimplementation of [Joondalup Timetable](https://github.com/T0mDrummond86/timetabler) (desktop). The desktop app remains the reference UI; this repo reuses its **Python domain layer** behind a FastAPI API and React frontend.

## Stack

| Layer | Technology |
|-------|------------|
| Domain | Ported `timetable/core`, `timetable/solver`, `timetable/io` (no Qt) |
| API | FastAPI, SQLAlchemy, Alembic, PostgreSQL |
| Jobs | Redis + RQ (solver worker — Phase 5) |
| UI | React 18, TypeScript, Vite, TanStack Query |

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

| Phase | Scope |
|-------|--------|
| **0** (now) | Repo bootstrap, domain copy, health API, React shell |
| **1** | Auth, orgs, sessions, `session_id` tenancy in Postgres |
| **2** | Read-only timetable grid |
| **3** | Booking edit, move, undo |
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
