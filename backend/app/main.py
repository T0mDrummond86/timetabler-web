"""Timetabler web API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from timetable.constants import NUM_DAYS, NUM_SLOTS

from .config import settings
from .database import check_database, create_all_tables
from .routers import (
    auth,
    bookings,
    changelog,
    entities,
    global_sessions,
    import_export,
    laps,
    orgs,
    sessions,
    timetable,
    violations,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        create_all_tables()
    yield


_docs_url = "/docs" if settings.expose_api_docs else None
_redoc_url = "/redoc" if settings.expose_api_docs else None
_openapi_url = "/openapi.json" if settings.expose_api_docs else None

app = FastAPI(
    title="Timetabler API",
    version="0.7.0",
    description="Multi-tenant web API for Joondalup Timetable",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > settings.max_upload_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large (max {settings.max_upload_bytes // (1024 * 1024)} MB)"},
                )
    return await call_next(request)


app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(sessions.router)
app.include_router(global_sessions.router)
app.include_router(entities.router)
app.include_router(import_export.router)
app.include_router(changelog.router)
app.include_router(bookings.router)
app.include_router(timetable.router)
app.include_router(violations.router)
app.include_router(laps.router)


@app.exception_handler(LookupError)
async def lookup_error_handler(_request: Request, exc: LookupError):
    """Map service-layer LookupError to 404 so clients get JSON, not opaque 500s."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": "up" if check_database() else "down",
        "grid": {"days": NUM_DAYS, "slots": NUM_SLOTS},
        "phase": 9,
    }


@app.get("/")
def root():
    payload: dict = {
        "name": "Timetabler API",
        "health": "/health",
    }
    if settings.expose_api_docs:
        payload["docs"] = "/docs"
    return payload
