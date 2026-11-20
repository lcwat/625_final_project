"""SQLite job queue + results store.

Tables
------
jobs      one row per (run_tag, participant, session, slideshow); tracks status
          so a run can be resumed and failures retried.
results   the raw JSON returned by the model plus usage/latency metadata.
events    one row per scored event, flattened for easy querying/export.
caches    context-cache handles created for a run so they can be reused/deleted.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import config
from .data import Transcript

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    run_tag        TEXT NOT NULL,
    job_id         TEXT NOT NULL,
    participant_id INTEGER NOT NULL,
    session        INTEGER NOT NULL,
    slideshow      TEXT NOT NULL,
    cohort         TEXT NOT NULL,
    transcript     TEXT NOT NULL,
    word_count     INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending | done | failed
    attempts       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT,
    updated_at     TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (run_tag, job_id)
);
CREATE TABLE IF NOT EXISTS results (
    run_tag          TEXT NOT NULL,
    job_id           TEXT NOT NULL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    used_cache       INTEGER NOT NULL,
    raw_json         TEXT NOT NULL,
    prompt_tokens    INTEGER,
    cached_tokens    INTEGER,
    output_tokens    INTEGER,
    thinking_tokens  INTEGER,
    latency_s        REAL,
    scored_at        TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (run_tag, job_id)
);
CREATE TABLE IF NOT EXISTS events (
    run_tag          TEXT NOT NULL,
    job_id           TEXT NOT NULL,
    participant_id   INTEGER NOT NULL,
    session          INTEGER NOT NULL,
    slideshow        TEXT NOT NULL,
    event_id         INTEGER NOT NULL,
    event_json       TEXT NOT NULL,
    details_count    INTEGER NOT NULL,
    event_remembered INTEGER NOT NULL,
    PRIMARY KEY (run_tag, job_id, event_id)
);
CREATE TABLE IF NOT EXISTS caches (
    run_tag     TEXT NOT NULL,
    slideshow   TEXT NOT NULL,
    cache_name  TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (run_tag, slideshow)
);
"""


class Store:
    """Thread-safe (one connection per thread) wrapper around the SQLite file."""

    def __init__(self, path: Path = config.DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=60, isolation_level=None)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=60000")
            c.row_factory = sqlite3.Row
            self._local.conn = c
        yield c

    # ---- jobs ---------------------------------------------------------
    def add_jobs(self, transcripts: list[Transcript], run_tag: str = config.RUN_TAG) -> int:
        rows = [
            (run_tag, t.job_id, t.participant_id, t.session, t.slideshow, t.cohort,
             t.text, len(t.text.split()))
            for t in transcripts
        ]
        with self.conn() as c:
            before = c.execute("SELECT COUNT(*) FROM jobs WHERE run_tag=?", (run_tag,)).fetchone()[0]
            c.executemany(
                "INSERT OR IGNORE INTO jobs (run_tag, job_id, participant_id, session, slideshow, "
                "cohort, transcript, word_count) VALUES (?,?,?,?,?,?,?,?)", rows)
            after = c.execute("SELECT COUNT(*) FROM jobs WHERE run_tag=?", (run_tag,)).fetchone()[0]
        return after - before

    def pending_jobs(self, run_tag: str = config.RUN_TAG, include_failed: bool = True) -> list[sqlite3.Row]:
        statuses = ("pending", "failed") if include_failed else ("pending",)
        q = f"SELECT * FROM jobs WHERE run_tag=? AND status IN ({','.join('?' * len(statuses))}) " \
            "ORDER BY slideshow, session, participant_id"
        with self.conn() as c:
            return c.execute(q, (run_tag, *statuses)).fetchall()

    def job_counts(self, run_tag: str = config.RUN_TAG) -> dict[str, int]:
        with self.conn() as c:
            rows = c.execute("SELECT status, COUNT(*) n FROM jobs WHERE run_tag=? GROUP BY status",
                             (run_tag,)).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def mark_failed(self, run_tag: str, job_id: str, attempts: int, error: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE jobs SET status='failed', attempts=?, last_error=?, "
                      "updated_at=datetime('now') WHERE run_tag=? AND job_id=?",
                      (attempts, error[:2000], run_tag, job_id))

    # ---- results ------------------------------------------------------
    def save_result(self, run_tag: str, job: sqlite3.Row, parsed: dict, raw_json: str,
                    meta: dict, attempts: int) -> None:
        event_rows = [
            (run_tag, job["job_id"], job["participant_id"], job["session"], job["slideshow"],
             int(ev["event_id"]), json.dumps(ev, ensure_ascii=False),
             len(ev.get("unique_details") or []), int(bool(ev.get("event_remembered"))))
            for ev in parsed["events"]
        ]
        with self.conn() as c:
            c.execute("BEGIN")
            try:
                c.execute(
                    "INSERT OR REPLACE INTO results (run_tag, job_id, model, prompt_version, used_cache, "
                    "raw_json, prompt_tokens, cached_tokens, output_tokens, thinking_tokens, latency_s) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (run_tag, job["job_id"], meta["model"], meta["prompt_version"], int(meta["used_cache"]),
                     raw_json, meta.get("prompt_tokens"), meta.get("cached_tokens"),
                     meta.get("output_tokens"), meta.get("thinking_tokens"), meta.get("latency_s")))
                c.execute("DELETE FROM events WHERE run_tag=? AND job_id=?", (run_tag, job["job_id"]))
                c.executemany(
                    "INSERT INTO events (run_tag, job_id, participant_id, session, slideshow, event_id, "
                    "event_json, details_count, event_remembered) VALUES (?,?,?,?,?,?,?,?,?)", event_rows)
                c.execute("UPDATE jobs SET status='done', attempts=?, last_error=NULL, "
                          "updated_at=datetime('now') WHERE run_tag=? AND job_id=?",
                          (attempts, run_tag, job["job_id"]))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    def fetch_results(self, run_tag: str = config.RUN_TAG) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute(
                "SELECT j.*, r.model, r.prompt_version, r.used_cache, r.raw_json, r.prompt_tokens, "
                "r.cached_tokens, r.output_tokens, r.thinking_tokens, r.latency_s, r.scored_at "
                "FROM jobs j JOIN results r ON j.run_tag=r.run_tag AND j.job_id=r.job_id "
                "WHERE j.run_tag=? ORDER BY j.slideshow, j.session, j.participant_id", (run_tag,)).fetchall()

    # ---- caches -------------------------------------------------------
    def save_cache(self, run_tag: str, slideshow: str, cache_name: str, model: str) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO caches (run_tag, slideshow, cache_name, model) VALUES (?,?,?,?)",
                      (run_tag, slideshow, cache_name, model))

    def get_caches(self, run_tag: str) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT slideshow, cache_name FROM caches WHERE run_tag=?", (run_tag,)).fetchall()
        return {r["slideshow"]: r["cache_name"] for r in rows}

    def delete_cache_rows(self, run_tag: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM caches WHERE run_tag=?", (run_tag,))
