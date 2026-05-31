"""Application settings from environment."""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://timetabler:timetabler@localhost:5432/timetabler"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auto_create_tables: bool = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        auto = os.environ.get("AUTO_CREATE_TABLES")
        if auto is not None:
            self.auto_create_tables = auto.lower() in ("1", "true", "yes")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
