from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for

from zybooks_client import ZybooksClient, ZybooksError

DB_PATH = Path(os.getenv("ZYBOOKAUTO_DB", "zybookauto.db"))
SECRET_KEY = os.getenv("ZYBOOKAUTO_SECRET", "dev-only-change-me")

app = Flask(__name__)
app.secret_key = SECRET_KEY


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_code TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    section INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    error TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def set(self, key: str, value: str):
        with self.lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def enqueue(self, book_code: str, chapter: int, section: int, title: str) -> int:
        with self.lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO jobs(book_code, chapter, section, title, status) VALUES(?,?,?,?, 'queued')",
                (book_code, chapter, section, title),
            )
            return int(cur.lastrowid)

    def update_job(self, job_id: int, status: str, error: str | None = None):
        with self.lock, self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, job_id),
            )

    def jobs(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 200").fetchall()
        return [dict(r) for r in rows]

    def next_queued(self) -> dict[str, Any] | None:
        with self.lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id ASC LIMIT 1").fetchone()
            if not row:
                return None
            conn.execute("UPDATE jobs SET status='running', updated_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
        return dict(row)

    def clear_finished(self):
        with self.lock, self._conn() as conn:
            conn.execute("DELETE FROM jobs WHERE status IN ('done','submitted','failed','cancelled')")


store = Store(DB_PATH)
worker_stop = threading.Event()
worker_pause = threading.Event()
worker_pause.set()
worker_thread: threading.Thread | None = None
activity_lock = threading.Lock()
worker_activity: dict[str, Any] = {"stage": "idle"}


def set_activity(**kwargs):
    global worker_activity
    with activity_lock:
        worker_activity = kwargs


def build_client() -> ZybooksClient:
    email = store.get("email") or os.getenv("ZYBOOKS_EMAIL", "")
    password = store.get("password") or os.getenv("ZYBOOKS_PASSWORD", "")
    if not email or not password:
        raise ZybooksError("ZyBooks credentials are not configured")
    client = ZybooksClient(email, password)
    client.signin()
    return client


def worker_loop():
    while not worker_stop.is_set():
        worker_pause.wait(0.5)
        if not worker_pause.is_set() or worker_stop.is_set():
            continue

        job = store.next_queued()
        if not job:
            set_activity(stage="idle")
            time.sleep(1)
            continue

        base = {
            "job_id": job["id"],
            "book_code": job["book_code"],
            "chapter": job["chapter"],
            "section": job["section"],
            "title": job["title"],
        }

        try:
            set_activity(**base, stage="signing_in")
            client = build_client()
            set_activity(**base, stage="checking_progress")
            progress = client.get_section_progress(job["book_code"], job["chapter"], job["section"])
            if progress.get("complete"):
                store.update_job(job["id"], "done")
                set_activity(**base, stage="already_complete")
                continue

            min_delay = float(store.get("min_delay", "8"))
            max_delay = float(store.get("max_delay", "18"))
            retries = int(store.get("retries", "3"))

            def on_progress(event):
                set_activity(**base, **event)

            result = client.complete_section(
                job["book_code"],
                job["chapter"],
                job["section"],
                min_delay=min_delay,
                max_delay=max_delay,
                retries=retries,
                progress_callback=on_progress,
            )

            set_activity(**base, stage="verifying", **result)
            time.sleep(1)
            verify = client.get_section_progress(job["book_code"], job["chapter"], job["section"])
            if verify.get("complete"):
                store.update_job(job["id"], "done")
                set_activity(**base, stage="verified_complete", **result)
            elif result.get("accepted"):
                store.update_job(job["id"], "submitted", "Submission accepted; read-back endpoint did not expose a completed state")
                set_activity(**base, stage="submitted_unverified", **result)
            else:
                store.update_job(job["id"], "failed", "No accepted activity submissions were recorded")
                set_activity(**base, stage="failed")
        except Exception as exc:
            store.update_job(job["id"], "failed", str(exc))
            set_activity(**base, stage="failed", error=str(exc))


def ensure_worker():
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        return
    worker_stop.clear()
    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()


@app.get("/")
def index():
    return render_template(
        "index.html",
        min_delay=store.get("min_delay", "8"),
        max_delay=store.get("max_delay", "18"),
        retries=store.get("retries", "3"),
    )


@app.post("/settings")
def settings():
    for key in ("email", "password", "min_delay", "max_delay", "retries"):
        if key in request.form and request.form[key] != "":
            store.set(key, request.form[key])
    return redirect(url_for("index"))


@app.get("/api/books")
def api_books():
    try:
        client = build_client()
        return jsonify(client.get_books())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/book/<code>")
def api_book(code: str):
    try:
        client = build_client()
        return jsonify(client.get_book_outline_with_progress(code))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/queue")
def api_queue():
    payload = request.get_json(force=True)
    code = payload["book_code"]
    items = payload.get("items", [])
    ids = [store.enqueue(code, int(i["chapter"]), int(i["section"]), i.get("title", "")) for i in items]
    ensure_worker()
    return jsonify({"queued": len(ids), "ids": ids})


@app.get("/api/jobs")
def api_jobs():
    with activity_lock:
        activity = dict(worker_activity)
    return jsonify({"jobs": store.jobs(), "paused": not worker_pause.is_set(), "activity": activity})


@app.post("/api/jobs/pause")
def api_pause():
    worker_pause.clear()
    set_activity(stage="paused")
    return jsonify({"ok": True})


@app.post("/api/jobs/resume")
def api_resume():
    ensure_worker()
    worker_pause.set()
    return jsonify({"ok": True})


@app.post("/api/jobs/stop")
def api_stop():
    worker_pause.clear()
    with store.lock, store._conn() as conn:
        conn.execute("UPDATE jobs SET status='cancelled' WHERE status='queued'")
    set_activity(stage="paused")
    return jsonify({"ok": True})


@app.post("/api/jobs/clear")
def api_clear():
    store.clear_finished()
    return jsonify({"ok": True})


if __name__ == "__main__":
    ensure_worker()
    app.run(host=os.getenv("APP_HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8765")), debug=False)
