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


app = FastAPI(
    title="Timetabler API",
    version="0.7.0",
    description="Multi-tenant web API for Joondalup Timetable",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {
        "name": "Timetabler API",
        "docs": "/docs",
        "health": "/health",
    }
