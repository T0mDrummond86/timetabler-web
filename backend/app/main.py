"""Timetabler web API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from timetable.constants import NUM_DAYS, NUM_SLOTS

from .config import settings
from .database import check_database, create_all_tables
from .routers import auth, orgs, sessions, timetable


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        create_all_tables()
    yield


app = FastAPI(
    title="Timetabler API",
    version="0.2.0",
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
app.include_router(timetable.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": "up" if check_database() else "down",
        "grid": {"days": NUM_DAYS, "slots": NUM_SLOTS},
        "phase": 2,
    }


@app.get("/")
def root():
    return {
        "name": "Timetabler API",
        "docs": "/docs",
        "health": "/health",
    }
