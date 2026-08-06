"""
Centralized configuration for the Orders Dashboard app.

All environment-variable reads happen here so the rest of the codebase
never touches os.environ directly, and misconfiguration fails fast and
loudly at import time instead of surfacing as a confusing runtime error
deep inside a request.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    # Injected automatically by the `resources.postgres` binding on the
    # apps.lakebase_app resource in databricks.yml when running as a
    # Databricks App. For local dev, set these yourself (see .env.example).
    pg_host: str | None = field(default_factory=lambda: os.environ.get("PGHOST"))
    pg_port: str = field(default_factory=lambda: os.environ.get("PGPORT", "5432"))
    pg_database: str = field(default_factory=lambda: os.environ.get("PGDATABASE", "databricks_postgres"))
    pg_user: str | None = field(default_factory=lambda: os.environ.get("PGUSER"))
    pg_sslmode: str = field(default_factory=lambda: os.environ.get("PGSSLMODE", "require"))
    pg_appname: str = field(default_factory=lambda: os.environ.get("PGAPPNAME", "orders-dashboard"))

    # Endpoint identifier used to mint Lakebase OAuth database credentials.
    endpoint_name: str | None = field(
        default_factory=lambda: os.environ.get("PGENDPOINT") or os.environ.get("LAKEBASE_ENDPOINT_NAME")
    )

    # Connection pool tuning — override via env for larger deployments.
    pool_min_size: int = field(default_factory=lambda: _env_int("POOL_MIN_SIZE", 1))
    pool_max_size: int = field(default_factory=lambda: _env_int("POOL_MAX_SIZE", 10))
    pool_timeout_s: float = field(default_factory=lambda: _env_float("POOL_TIMEOUT_S", 30))

    # Credential-minting retry tuning.
    credential_retries: int = field(default_factory=lambda: _env_int("CREDENTIAL_RETRIES", 3))
    credential_retry_backoff_s: float = field(default_factory=lambda: _env_float("CREDENTIAL_RETRY_BACKOFF_S", 0.5))

    # Flask secret key. Generated randomly if not provided; set SECRET_KEY
    # explicitly if you need flashed messages / sessions to survive restarts.
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY") or secrets.token_hex(32))

    # Pagination defaults for the dashboard views / JSON API.
    default_page_size: int = field(default_factory=lambda: _env_int("DEFAULT_PAGE_SIZE", 10))
    max_page_size: int = field(default_factory=lambda: _env_int("MAX_PAGE_SIZE", 100))

    @property
    def is_db_configured(self) -> bool:
        return bool(self.pg_host and self.pg_user)

    def conninfo(self) -> str:
        return (
            f"dbname={self.pg_database} user={self.pg_user} host={self.pg_host} "
            f"port={self.pg_port} sslmode={self.pg_sslmode} application_name={self.pg_appname}"
        )


settings = Settings()
