import importlib

import pytest

pytest.importorskip("flask")


@pytest.fixture
def client(db_module, monkeypatch):
    import app as app_module

    importlib.reload(app_module)  # pick up the patched db module cleanly
    monkeypatch.setattr(app_module, "db", db_module)
    monkeypatch.setattr(app_module.app, "_lakebase_ready", True, raising=False)  # skip pool startup
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c, app_module


def test_index_renders(client):
    c, _ = client
    resp = c.get("/")
    assert resp.status_code == 200
    assert b"Orders Dashboard" in resp.data


def test_healthz_reports_status(client):
    c, _ = client
    resp = c.get("/healthz")
    assert resp.status_code in (200, 503)
    assert resp.json["status"] in ("ok", "degraded")


def test_add_note_requires_csrf_token(client):
    c, _ = client
    resp = c.post("/notes", data={"content": "no token"}, follow_redirects=True)
    # Missing/invalid CSRF token should not error out, just no-op with a flash.
    assert resp.status_code == 200


def test_add_note_with_valid_csrf(client):
    c, app_module = client
    with c.session_transaction() as sess:
        sess["csrf_token"] = "test-token"
    resp = c.post(
        "/notes",
        data={"content": "hello world", "csrf_token": "test-token"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    api_resp = c.get("/api/notes")
    assert any(n["content"] == "hello world" for n in api_resp.json["items"])


def test_api_orders_json_shape(client):
    c, _ = client
    resp = c.get("/api/orders")
    assert resp.status_code == 200
    body = resp.json
    assert "items" in body and "total" in body and "total_pages" in body
    if body["items"]:
        row = body["items"][0]
        assert set(row.keys()) == {
            "order_id", "customer", "item", "quantity", "amount", "status", "ordered_at",
        }
