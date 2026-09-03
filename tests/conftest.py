"""
Shared test fixtures.

Tests run against an in-memory fake of the psycopg pool so the suite never
needs network access or a real Lakebase project — fast, deterministic, and
safe to run in CI on every PR.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app_src"))


class _UndefinedTableError(Exception):
    """Fallback error used when psycopg isn't installed in test env."""


def _new_undefined_table_error() -> Exception:
    try:
        import psycopg

        return psycopg.errors.UndefinedTable()
    except ModuleNotFoundError:
        return _UndefinedTableError()


def _install_test_stubs() -> None:
    if "psycopg" not in sys.modules:
        psycopg_stub = types.ModuleType("psycopg")

        class _StubConnection:
            @classmethod
            def connect(cls, conninfo="", **kwargs):
                return None

        psycopg_stub.Connection = _StubConnection
        psycopg_stub.errors = types.SimpleNamespace(UndefinedTable=_UndefinedTableError)
        sys.modules["psycopg"] = psycopg_stub

    if "psycopg_pool" not in sys.modules:
        psycopg_pool_stub = types.ModuleType("psycopg_pool")

        class _StubConnectionPool:
            def __init__(self, *args, **kwargs):
                pass

            def open(self, *args, **kwargs):
                return None

            def connection(self, *args, **kwargs):
                raise RuntimeError("Stub pool should be replaced by FakePool in tests")

        psycopg_pool_stub.ConnectionPool = _StubConnectionPool
        sys.modules["psycopg_pool"] = psycopg_pool_stub

    if "databricks" not in sys.modules:
        databricks_stub = types.ModuleType("databricks")
        sdk_stub = types.ModuleType("databricks.sdk")

        class _StubWorkspaceClient:
            def __init__(self):
                self.postgres = types.SimpleNamespace(
                    generate_database_credential=lambda endpoint: types.SimpleNamespace(token="stub-token")
                )

        sdk_stub.WorkspaceClient = _StubWorkspaceClient
        databricks_stub.sdk = sdk_stub
        sys.modules["databricks"] = databricks_stub
        sys.modules["databricks.sdk"] = sdk_stub


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        q = " ".join(query.split()).lower()
        params = params or ()

        if q.startswith("select count(*) from notes"):
            return self._select_notes_count()
        if q.startswith("select id, content, created_at from notes"):
            return self._select_notes_page(params)
        if q.startswith("insert into notes"):
            return self._insert_note(params)
        if q.startswith("delete from notes"):
            return self._delete_note(params)
        if "count(*) from orders_synced" in q:
            self._ensure_orders_table()
            self._result = [(len(self.conn.db.orders),)]
            return
        if "from orders_synced" in q:
            self._ensure_orders_table()
            rows = self.conn.db.orders
            *_, limit, offset = params
            self._result = rows[offset: offset + limit]
            return
        if q.startswith("select 1"):
            self._result = [(1,)]
            return

        self._result = []

    def _select_notes_count(self):
        self._result = [(len(self.conn.db.notes),)]

    def _select_notes_page(self, params):
        rows = sorted(self.conn.db.notes, key=lambda n: n[0], reverse=True)
        limit, offset = params
        self._result = rows[offset: offset + limit]

    def _insert_note(self, params):
        from datetime import UTC, datetime

        (content,) = params
        self.conn.db.next_note_id += 1
        self.conn.db.notes.append(
            (self.conn.db.next_note_id, content, datetime.now(UTC))
        )

    def _delete_note(self, params):
        (note_id,) = params
        self.conn.db.notes = [n for n in self.conn.db.notes if n[0] != note_id]

    def _ensure_orders_table(self):
        if not self.conn.db.orders_table_exists:
            raise self.conn.db.undefined_table_error

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result


class FakeConnection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        with self.cursor() as cur:
            cur.execute(query, params)
        return None

    def cursor(self):
        return FakeCursor(self)


class FakeDB:
    """In-memory notes/orders store standing in for Postgres."""

    def __init__(self):
        from datetime import UTC, datetime

        self.notes = []
        self.next_note_id = 0
        self.orders = [
            (1, "Ava Chen", "Wireless Mouse", 2, 39.98, "shipped", datetime(2026, 1, 1, tzinfo=UTC)),
            (2, "Marcus Diallo", "Mechanical KB", 1, 129.00, "shipped", datetime(2026, 1, 2, tzinfo=UTC)),
        ]
        self.orders_table_exists = True
        self.undefined_table_error = _new_undefined_table_error()


class FakePool:
    def __init__(self, db):
        self.db = db

    def connection(self, timeout=None):
        return FakeConnection(self.db)


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def db_module(fake_db, monkeypatch):
    _install_test_stubs()
    import db as db_mod

    monkeypatch.setattr(db_mod, "pool", FakePool(fake_db))
    return db_mod
