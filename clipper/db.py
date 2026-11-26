"""Tiny SQLite store for jobs and clips."""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    num_clips INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT DEFAULT '',
    error TEXT DEFAULT '',
    title TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    score INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    hook TEXT DEFAULT '',
    title TEXT DEFAULT '',
    caption TEXT DEFAULT '',
    hashtags TEXT DEFAULT '',
    file TEXT DEFAULT '',
    thumb TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'rendering',
    error TEXT DEFAULT '',
    uploads TEXT DEFAULT '{}',
    created_at REAL NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript(SCHEMA)
        # Jobs that were mid-way when the app was closed get re-queued.
        c.execute("UPDATE jobs SET status='queued', stage='' WHERE status='running'")
        # Uploads that were mid-way are marked failed so they can be retried.
        for row in c.execute("SELECT id, uploads FROM clips").fetchall():
            ups = json.loads(row["uploads"] or "{}")
            changed = False
            for p, u in ups.items():
                if u.get("status") == "uploading":
                    u.update(status="failed", error="App was closed during upload")
                    changed = True
            if changed:
                c.execute("UPDATE clips SET uploads=? WHERE id=?", (json.dumps(ups), row["id"]))


def _row(r):
    if r is None:
        return None
    d = dict(r)
    if "uploads" in d:
        d["uploads"] = json.loads(d["uploads"] or "{}")
    return d


def create_job(url: str, num_clips: int) -> int:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO jobs (url, num_clips, created_at) VALUES (?,?,?)",
            (url, num_clips, time.time()),
        )
        return cur.lastrowid


def update_job(job_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def get_job(job_id: int):
    with _lock, _conn() as c:
        return _row(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def list_jobs():
    with _lock, _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()]


def next_queued_job():
    with _lock, _conn() as c:
        return _row(c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone())


def create_clip(job_id: int, **fields) -> int:
    fields = {**fields, "job_id": job_id, "created_at": time.time()}
    cols = ", ".join(fields)
    qs = ", ".join("?" for _ in fields)
    with _lock, _conn() as c:
        return c.execute(f"INSERT INTO clips ({cols}) VALUES ({qs})", tuple(fields.values())).lastrowid


def update_clip(clip_id: int, **fields) -> None:
    if not fields:
        return
    if "uploads" in fields and not isinstance(fields["uploads"], str):
        fields["uploads"] = json.dumps(fields["uploads"])
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE clips SET {cols} WHERE id=?", (*fields.values(), clip_id))


def set_upload_status(clip_id: int, platform: str, **info) -> None:
    """Atomically update one platform's upload status on a clip."""
    with _lock, _conn() as c:
        row = c.execute("SELECT uploads FROM clips WHERE id=?", (clip_id,)).fetchone()
        ups = json.loads(row["uploads"] or "{}")
        ups[platform] = {**ups.get(platform, {}), **info}
        c.execute("UPDATE clips SET uploads=? WHERE id=?", (json.dumps(ups), clip_id))


def get_clip(clip_id: int):
    with _lock, _conn() as c:
        return _row(c.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone())


def list_clips(job_id: int | None = None):
    q = "SELECT * FROM clips"
    args: tuple = ()
    if job_id is not None:
        q += " WHERE job_id=?"
        args = (job_id,)
    q += " ORDER BY job_id DESC, score DESC"
    with _lock, _conn() as c:
        return [_row(r) for r in c.execute(q, args).fetchall()]
