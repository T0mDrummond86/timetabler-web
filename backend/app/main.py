"""Timetabler web API — Phase 0 bootstrap."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from timetable.constants import NUM_DAYS, NUM_SLOTS

from .config import settings
from .db import check_database

app = FastAPI(
    title="Timetabler API",
    version="0.1.0",
    description="Multi-tenant web API for Joondalup Timetable",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": "up" if check_database() else "down",
        "grid": {"days": NUM_DAYS, "slots": NUM_SLOTS},
    }


@app.get("/")
def root():
    return {
        "name": "Timetabler API",
        "docs": "/docs",
        "health": "/health",
    }
