"""
Orders Dashboard — a small Databricks App backed by Lakebase.

- Displays rows from `orders_synced`, a Unity Catalog Delta table that
  Lakebase continuously syncs into Postgres (read-only, no ETL code here).
- Lets users add/delete free-text "notes" stored directly in Postgres,
  demonstrating normal OLTP read/write against Lakebase.
- Exposes small JSON endpoints (/api/orders, /api/notes) that the front end
  polls so the dashboard feels live without a full page reload.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g

import db
from config import settings
from serializers import note_to_dict, order_to_dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = settings.secret_key


# ---------------------------------------------------------------------------
# Request lifecycle: lazy startup, request-id logging, CSRF token plumbing
# ---------------------------------------------------------------------------

@app.before_request
def _startup_once():
    # Flask 3 removed before_first_request; guard with an app attribute instead.
    if not getattr(app, "_lakebase_ready", False):
        db.init_pool()
        db.run_migrations()
        app._lakebase_ready = True


@app.before_request
def _tag_request():
    g.request_id = request.headers.get("X-Request-Id", str(uuid.uuid4())[:8])
    g.start_time = time.time()


@app.after_request
def _log_and_tag_response(response):
    duration_ms = (time.time() - g.get("start_time", time.time())) * 1000
    response.headers["X-Request-Id"] = g.get("request_id", "-")
    log.info(
        "[%s] %s %s -> %s (%.1fms)",
        g.get("request_id", "-"),
        request.method,
        request.path,
        response.status_code,
        duration_ms,
    )
    return response


def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = _csrf_token


def _require_csrf():
    token = session.get("csrf_token")
    submitted = request.form.get("csrf_token")
    return bool(token and submitted and secrets.compare_digest(token, submitted))


def _parse_list_query_args() -> tuple[int, str | None]:
    page = max(1, request.args.get("page", 1, type=int))
    search = (request.args.get("q") or "").strip() or None
    return page, search


@app.errorhandler(db.CredentialError)
def _handle_credential_error(exc):
    log.error("Lakebase credential error: %s", exc)
    return {"error": "Temporarily unable to reach the database. Please retry."}, 503


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    page, search = _parse_list_query_args()
    orders_page, orders_error = db.fetch_orders(page=page, search=search)
    notes_page = db.fetch_notes(page=1)
    return render_template(
        "index.html",
        orders_page=orders_page,
        orders_error=orders_error,
        notes_page=notes_page,
        search=search or "",
    )


@app.route("/notes", methods=["POST"])
def add_note():
    if not _require_csrf():
        flash("Session expired, please try again.")
        return redirect(url_for("index"))
    content = (request.form.get("content") or "").strip()
    try:
        db.insert_note(content)
    except ValueError:
        flash("Note can't be empty.")
    return redirect(url_for("index"))


@app.route("/notes/<int:note_id>/delete", methods=["POST"])
def remove_note(note_id):
    if not _require_csrf():
        flash("Session expired, please try again.")
        return redirect(url_for("index"))
    db.delete_note(note_id)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# JSON API — used by static/app.js to live-refresh the dashboard
# ---------------------------------------------------------------------------

@app.route("/api/orders")
def api_orders():
    page, search = _parse_list_query_args()
    orders_page, error = db.fetch_orders(page=page, search=search)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(
        {
            "items": [order_to_dict(order) for order in orders_page.items],
            "page": orders_page.page,
            "total_pages": orders_page.total_pages,
            "total": orders_page.total,
        }
    )


@app.route("/api/notes")
def api_notes():
    notes_page = db.fetch_notes(page=1)
    return jsonify(
        {
            "items": [note_to_dict(note) for note in notes_page.items],
            "total": notes_page.total,
        }
    )


@app.route("/healthz")
def healthz():
    db_ok = db.healthcheck() if settings.is_db_configured else False
    status = "ok" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return jsonify({"status": status, "db_configured": settings.is_db_configured}), code


if __name__ == "__main__":
    # Local dev only. In Databricks Apps, gunicorn runs `app:app` (see
    # databricks.yml / app.yaml).
    app.run(host="0.0.0.0", port=8000, debug=True)
