# Security findings register

Quick-wins pass for timetabler-web. Severity: **Critical / High / Medium / Low**.

## Fixed in this pass

| ID | Severity | Finding | Remediation | Status |
|----|----------|---------|-------------|--------|
| SEC-01 | Critical | Default `JWT_SECRET` usable in production | Startup validation rejects known placeholders when `ENVIRONMENT=production` | Fixed |
| SEC-02 | High | `/docs` and `/openapi.json` exposed | Disabled when `ENVIRONMENT=production` | Fixed |
| SEC-03 | High | `POST /sessions/{id}/seed-demo` available in prod | Returns 404 in production | Fixed |
| SEC-04 | High | Unbounded file/JSON uploads (memory DoS) | 50 MB cap on uploads and request bodies (`MAX_UPLOAD_BYTES`) | Fixed |
| SEC-05 | High | No rate limits on `/auth/login` and `/auth/register` | In-memory limiter: 10 req/min per IP | Fixed |
| SEC-06 | Medium | Open registration in production | `ALLOW_REGISTRATION=false` returns 403 | Fixed |
| SEC-07 | Medium | `AUTO_CREATE_TABLES=true` unsafe in prod | Startup validation fails if true in production | Fixed |

## Cross-tenant spot check (5 routes)

Tested in [`backend/tests/test_security_quick_wins.py`](../backend/tests/test_security_quick_wins.py):

| Route | Result |
|-------|--------|
| `GET /sessions/{id}/timetable` | 404 for other org’s session |
| `POST /sessions/{id}/import` | 404 (or 400/413) for other org’s session |
| `GET /sessions/{id}/export/admin` | 404 for other org’s session |
| `POST /sessions/{id}/bookings` | 404 for other org’s session |
| `PUT /global-sessions/{id}/members` | 404 for other org’s global session |

No IDOR bugs found in this spot check.

## Dependency scans

### npm audit (frontend)

- **2 moderate** (no high/critical): `vite` path traversal (≤6.4.1), `esbuild` dev-server issue (transitive via Vite)
- **Action:** Dev-only risk while using `npm run dev`. Production static build does not run the Vite dev server. Upgrade Vite to 6.4.3+ when convenient (semver-major).

### pip-audit (backend)

- **12 advisories** in 5 packages (no critical flagged by tool):
  - `python-multipart` 0.0.20 — multiple GHSA (fix 0.0.27+)
  - `starlette` 0.49.3 — PYSEC-2026-161 (fix 1.0.1)
  - `pillow` 11.3.0 — several (transitive via reportlab; fix 12.2.0)
  - `pytest` 8.4.2 — GHSA-6w46-j5rx-g56g (dev/test only)
  - `python-dotenv` 1.2.1 — GHSA-mf9w-mj56-hr94
- **Action:** Bump `python-multipart` pin on next dependency refresh; split `pytest` to dev-only requirements for production images.

## Deferred (not low-hanging fruit)

| ID | Severity | Finding | Why deferred |
|----|----------|---------|--------------|
| SEC-D01 | High | JWT stored in `localStorage` | Requires httpOnly cookie session redesign + XSS hardening |
| SEC-D02 | Medium | 7-day JWT, no server-side revocation | Needs refresh tokens or denylist |
| SEC-D03 | Medium | App-layer tenancy only (no Postgres RLS) | Systematic route audit or RLS migration |
| SEC-D04 | Medium | No CSP / HSTS / security headers in app | Configure at reverse proxy + frontend asset policy |
| SEC-D05 | Low | `viewer` vs `editor` role inconsistency | Product decision + router sweep |
| SEC-D06 | Low | In-memory rate limiter not shared across workers | Use Redis-backed limiter when scaling horizontally |

## Accepted risks (document)

| Item | Notes |
|------|-------|
| Dev Compose exposes DB/Redis ports | Acceptable for local dev only; see [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) |
| Vite/esbuild moderate CVEs | Affects dev server, not production static assets |
