"""Application settings from environment."""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# Known placeholder secrets — must not be used when ENVIRONMENT=production.
_INSECURE_JWT_SECRETS = frozenset(
    {
        "change-me-in-production",
        "dev-secret-change-in-production",
        "test-secret",
        "audit-secret",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://timetabler:timetabler@localhost:5432/timetabler"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auto_create_tables: bool = True
    environment: str = "development"
    allow_registration: bool = True
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    auth_rate_limit_requests: int = 10
    auth_rate_limit_window_seconds: int = 60
    violations_cache_ttl_seconds: int = 3600

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        elif self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace(
                "postgres://", "postgresql+psycopg://", 1
            )
        auto = os.environ.get("AUTO_CREATE_TABLES")
        if auto is not None and "auto_create_tables" not in kwargs:
            self.auto_create_tables = auto.lower() in ("1", "true", "yes")
        env = os.environ.get("ENVIRONMENT")
        if env is not None and "environment" not in kwargs:
            self.environment = env.strip().lower()
        reg = os.environ.get("ALLOW_REGISTRATION")
        if reg is not None and "allow_registration" not in kwargs:
            self.allow_registration = reg.lower() in ("1", "true", "yes")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def expose_api_docs(self) -> bool:
        return not self.is_production


def validate_settings(cfg: Settings) -> None:
    """Fail fast on unsafe production configuration."""
    if cfg.is_production:
        if cfg.jwt_secret in _INSECURE_JWT_SECRETS:
            raise RuntimeError(
                "JWT_SECRET must be set to a strong random value in production "
                "(placeholder secrets are not allowed)"
            )
        if cfg.auto_create_tables:
            raise RuntimeError(
                "AUTO_CREATE_TABLES must be false in production; use Alembic migrations"
            )


settings = Settings()
validate_settings(settings)
