"""
Lakebase Postgres connection handling for the Orders Dashboard app.

Databricks Apps authenticate to Lakebase using short-lived OAuth tokens
(1 hour lifetime). Rather than fetch a token once, we generate a *fresh*
token every time the connection pool opens a new physical connection, by
subclassing psycopg.Connection and overriding connect(). This is the
pattern documented at:
  https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/tutorial-databricks-apps-autoscaling

Optimizations over the minimal version:
  - Retries with backoff when minting a credential or opening a connection,
    since a single transient failure shouldn't take the whole app down.
  - Keyset-friendly pagination + a simple search filter on the orders view.
  - An index on notes(created_at) so the "recent notes" query stays cheap
    as the table grows.
  - All tunables come from config.Settings instead of scattered env reads.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import psycopg
from config import settings
from databricks.sdk import WorkspaceClient
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

_workspace_client: WorkspaceClient | None = None


def _get_workspace_client() -> WorkspaceClient:
    global _workspace_client
    if _workspace_client is None:
        _workspace_client = WorkspaceClient()
    return _workspace_client


class CredentialError(RuntimeError):
    """Raised when a Lakebase database credential can't be minted after retries."""


def _generate_credential_with_retry():
    last_exc: Exception | None = None
    for attempt in range(1, settings.credential_retries + 1):
        try:
            return _get_workspace_client().postgres.generate_database_credential(
                endpoint=settings.endpoint_name
            )
        except Exception as exc:  # noqa: BLE001 - we deliberately want to retry on anything
            last_exc = exc
            log.warning(
                "generate_database_credential attempt %d/%d failed: %s",
                attempt,
                settings.credential_retries,
                exc,
            )
            if attempt < settings.credential_retries:
                time.sleep(settings.credential_retry_backoff_s * attempt)
    raise CredentialError(
        f"Failed to mint a Lakebase database credential after {settings.credential_retries} attempts"
    ) from last_exc


class OAuthConnection(psycopg.Connection):
    """A psycopg Connection that mints a fresh Lakebase OAuth token on every
    new physical connection, instead of reusing a static password."""

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        if not settings.endpoint_name:
            raise RuntimeError(
                "No Lakebase endpoint configured. Set PGENDPOINT (injected "
                "automatically inside a Databricks App) or LAKEBASE_ENDPOINT_NAME "
                "for local development."
            )
        credential = _generate_credential_with_retry()
        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)


# A single process-wide pool. psycopg_pool lazily opens connections and
# recycles them, calling OAuthConnection.connect() (and therefore minting a
# fresh token) each time a brand-new physical connection is needed.
pool = ConnectionPool(
    conninfo=settings.conninfo() if settings.is_db_configured else "",
    connection_class=OAuthConnection,
    min_size=settings.pool_min_size,
    max_size=settings.pool_max_size,
    open=False,  # opened explicitly at app startup, see app.py
    kwargs={"autocommit": True},
)


def init_pool():
    if settings.is_db_configured:
        pool.open(wait=True, timeout=settings.pool_timeout_s)
        log.info(
            "Lakebase connection pool opened (host=%s db=%s min=%d max=%d)",
            settings.pg_host,
            settings.pg_database,
            settings.pool_min_size,
            settings.pool_max_size,
        )
    else:
        log.warning("Lakebase connection env vars missing; pool not opened.")


def run_migrations():
    """Idempotently create/upgrade the app's own schema on first boot."""
    with pool.connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id         BIGSERIAL PRIMARY KEY,
                content    TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS notes_created_at_idx ON notes (created_at DESC)"
        )


def healthcheck() -> bool:
    try:
        with pool.connection(timeout=5) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        return False


@dataclass
class Page:
    items: list
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


def _normalize_pagination(page: int, page_size: int | None) -> tuple[int, int, int]:
    page = max(1, page)
    normalized_page_size = min(page_size or settings.default_page_size, settings.max_page_size)
    offset = (page - 1) * normalized_page_size
    return page, normalized_page_size, offset


def _build_orders_filter(search: str | None) -> tuple[str, list[str]]:
    if not search:
        return "", []
    where_clause = "WHERE customer ILIKE %s OR item ILIKE %s OR status ILIKE %s"
    like = f"%{search}%"
    return where_clause, [like, like, like]


def fetch_notes(page: int = 1, page_size: int | None = None) -> Page:
    page, page_size, offset = _normalize_pagination(page, page_size)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM notes")
            count_row = cur.fetchone()
            total = count_row[0] if count_row else 0
            cur.execute(
                "SELECT id, content, created_at FROM notes "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (page_size, offset),
            )
            rows = cur.fetchall()
    return Page(items=rows, total=total, page=page, page_size=page_size)


def insert_note(content: str):
    content = content.strip()[:280]
    if not content:
        raise ValueError("Note content cannot be empty")
    with pool.connection() as conn:
        conn.execute("INSERT INTO notes (content) VALUES (%s)", (content,))


def delete_note(note_id: int):
    with pool.connection() as conn:
        conn.execute("DELETE FROM notes WHERE id = %s", (note_id,))


def fetch_orders(page: int = 1, page_size: int | None = None, search: str | None = None):
    """Read from the continuously-synced `orders_synced` table.

    This table is created and kept up to date by the postgres_synced_tables
    resource in databricks.yml — no writes happen here, Lakebase handles
    the sync from the Unity Catalog Delta table automatically.

    Supports a simple case-insensitive search across customer/item/status,
    and offset pagination for larger order volumes.
    """
    page, page_size, offset = _normalize_pagination(page, page_size)
    where_clause, params = _build_orders_filter(search)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"SELECT count(*) FROM orders_synced {where_clause}", params)
                count_row = cur.fetchone()
                total = count_row[0] if count_row else 0
                cur.execute(
                    f"""
                    SELECT order_id, customer, item, quantity, amount, status, ordered_at
                    FROM orders_synced
                    {where_clause}
                    ORDER BY ordered_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*params, page_size, offset),
                )
                rows = cur.fetchall()
                return Page(items=rows, total=total, page=page, page_size=page_size), None
            except psycopg.errors.UndefinedTable:
                return (
                    Page(items=[], total=0, page=1, page_size=page_size),
                    "orders_synced table not found yet. Deploy the bundle and "
                    "wait for the initial sync to complete (see setup/ for the "
                    "source table script).",
                )
