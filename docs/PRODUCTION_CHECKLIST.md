# Production deployment checklist

Use this when deploying **timetabler-web** to the internet. The repo’s [`docker-compose.yml`](../docker-compose.yml) is for **local development only**.

## Secrets and environment

| Setting | Dev Compose default | Production requirement |
|---------|---------------------|------------------------|
| `JWT_SECRET` | `dev-secret-change-in-production` | Strong random value (32+ bytes). App **refuses to start** if a known placeholder is used when `ENVIRONMENT=production`. |
| `ENVIRONMENT` | unset (`development`) | `production` |
| `AUTO_CREATE_TABLES` | `true` | `false` — run Alembic migrations instead |
| `ALLOW_REGISTRATION` | `true` | `false` until invite-only registration exists (optional but recommended) |

## Network and TLS

| Control | Dev Compose | Production requirement |
|---------|-------------|------------------------|
| Postgres port | `5432` published to host | Private network only; no public exposure |
| Redis port | `6379` published to host | Private network only; enable Redis AUTH |
| API | `uvicorn --reload` via volume mount | Production ASGI workers, no `--reload` |
| Frontend | `npm run dev` (Vite HMR) | Static build served behind HTTPS reverse proxy |
| TLS | None | HTTPS everywhere; enable HSTS at the proxy |

## API hardening (code-enforced when `ENVIRONMENT=production`)

- `/docs`, `/redoc`, `/openapi.json` are **disabled**
- `POST /sessions/{id}/seed-demo` returns **404**
- Uploads and large JSON bodies capped at `MAX_UPLOAD_BYTES` (default 50 MB)
- `/auth/login` and `/auth/register` rate-limited (10 requests/min per IP by default)

## CORS

Set `CORS_ORIGINS` to your production frontend origin(s) only. Do not use `*` with `allow_credentials=True`.

Example:

```env
CORS_ORIGINS=https://timetable.example.edu.au
```

## Operational

- [ ] Encrypted database backups with tested restore
- [ ] Auth failure and import events logged (no passwords or JWTs in logs)
- [ ] Dependency scans (`npm audit`, `pip-audit`) run periodically
- [ ] Security headers (CSP, `X-Frame-Options`, `X-Content-Type-Options`) at reverse proxy — not yet in app code

## Quick smoke test after deploy

1. `GET /health` returns 200
2. `GET /docs` returns 404
3. `POST /auth/register` returns 403 if registration disabled
4. API refuses to start with default `JWT_SECRET` when `ENVIRONMENT=production`

## Render Blueprint (recommended)

The repo includes [`render.yaml`](../render.yaml) for a free-tier stack: Postgres + Docker API + static frontend.

Full walkthrough: [`DEPLOY_RENDER.md`](DEPLOY_RENDER.md).

Production API image: [`backend/Dockerfile.prod`](../backend/Dockerfile.prod) — no `--reload`, runs `alembic upgrade head` then `uvicorn` on `$PORT`.
