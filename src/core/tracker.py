"""SQLite application tracker.

Rules enforced here (not just by convention):
* one row per platform job id (`source:source_id`), plus cross-source fingerprint dedupe;
* `applied` can only be set with evidence: a confirmation text captured from the
  employer's page, or `method="user_confirmed"` from assist mode;
* every status change is written to an append-only `events` table.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

from src.core.models import Job, Status, TERMINAL

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    title TEXT, company TEXT, location TEXT, work_type TEXT, salary TEXT,
    url TEXT, apply_url TEXT, ats TEXT,
    description TEXT,
    score REAL,
    matched_skills TEXT,
    missing_skills TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    cover_letter TEXT,
    unanswered TEXT,
    found_at TEXT, updated_at TEXT,
    applied_at TEXT, apply_method TEXT, confirmation_text TEXT, evidence_dir TEXT,
    follow_up_date TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_fp ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT, ts TEXT, from_status TEXT, to_status TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS boards (
    ats TEXT, token TEXT, company TEXT, discovered_from TEXT, added_at TEXT,
    PRIMARY KEY (ats, token)
);
"""


class EvidenceRequired(ValueError):
    pass


class Tracker:
    def __init__(self, db_path: Path | str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ discovery
    def seen(self, job: Job) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM jobs WHERE key=? OR fingerprint=? LIMIT 1", (job.key, job.fingerprint))
        return cur.fetchone() is not None

    def add_found(self, job: Job) -> bool:
        """Insert a newly discovered job. Returns False if it (or a cross-posted twin) exists."""
        if self.seen(job):
            return False
        now = _now()
        self.conn.execute(
            """INSERT INTO jobs (key, source, source_id, fingerprint, title, company, location,
               work_type, salary, url, apply_url, description, status, found_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.key, job.source, job.source_id, job.fingerprint, job.title, job.company,
             job.location, job.work_type, job.salary, job.url, job.apply_url, job.description,
             Status.FOUND.value, now, now))
        self._event(job.key, None, Status.FOUND.value, job.url)
        self.conn.commit()
        return True

    def update_fields(self, key: str, **fields: Any) -> None:
        if not fields:
            return
        for k in ("matched_skills", "missing_skills", "unanswered"):
            if k in fields and not isinstance(fields[k], (str, type(None))):
                fields[k] = json.dumps(fields[k])
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE jobs SET {cols}, updated_at=? WHERE key=?",
                          (*fields.values(), _now(), key))
        self.conn.commit()

    # ------------------------------------------------------------------ status
    def set_status(self, key: str, status: Status, detail: str = "", *,
                   confirmation_text: Optional[str] = None, method: Optional[str] = None,
                   evidence_dir: Optional[str] = None, follow_up_days: int = 7,
                   **fields: Any) -> None:
        row = self.get(key)
        if row is None:
            raise KeyError(key)
        if status == Status.APPLIED:
            if not (confirmation_text or method == "user_confirmed"):
                raise EvidenceRequired(
                    f"{key}: refusing to mark APPLIED without a captured confirmation "
                    "or explicit user confirmation")
            fields.update(applied_at=_now(), apply_method=method or "auto",
                          confirmation_text=confirmation_text, evidence_dir=evidence_dir,
                          follow_up_date=(date.today() + timedelta(days=follow_up_days)).isoformat())
        elif evidence_dir:
            fields["evidence_dir"] = evidence_dir
        fields["status"] = status.value
        if detail:
            fields["reason"] = detail
        self.update_fields(key, **fields)
        self._event(key, row["status"], status.value, detail)
        self.conn.commit()

    # ------------------------------------------------------------------ queries
    def get(self, key: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()

    def by_status(self, *statuses: Status, order: str = "score DESC") -> list[sqlite3.Row]:
        q = ",".join("?" * len(statuses))
        return list(self.conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({q}) ORDER BY {order}",
            [s.value for s in statuses]))

    def applied_on(self, day: date) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM jobs WHERE status=? AND substr(applied_at,1,10)=? ORDER BY applied_at",
            (Status.APPLIED.value, day.isoformat())))

    def count_applied_today(self) -> int:
        return len(self.applied_on(date.today()))

    def follow_ups_due(self, today: Optional[date] = None) -> list[sqlite3.Row]:
        t = (today or date.today()).isoformat()
        return list(self.conn.execute(
            "SELECT * FROM jobs WHERE status=? AND follow_up_date<=? ORDER BY follow_up_date",
            (Status.APPLIED.value, t)))

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.conn.execute(
            "SELECT status, COUNT(*) FROM jobs GROUP BY status")}

    def events_for(self, key: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM events WHERE key=? ORDER BY id", (key,)))

    def is_open(self, key: str) -> bool:
        row = self.get(key)
        return row is not None and Status(row["status"]) not in TERMINAL

    # ------------------------------------------------------------------ ATS boards
    def add_board(self, ats: str, token: str, company: str = "", discovered_from: str = "") -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO boards VALUES (?,?,?,?,?)",
            (ats, token, company, discovered_from, _now()))
        self.conn.commit()
        return cur.rowcount > 0

    def boards(self, ats: str) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT token FROM boards WHERE ats=?", (ats,))]

    # ------------------------------------------------------------------ internals
    def _event(self, key: str, frm: Optional[str], to: str, detail: str) -> None:
        self.conn.execute("INSERT INTO events (key, ts, from_status, to_status, detail) VALUES (?,?,?,?,?)",
                          (key, _now(), frm, to, (detail or "")[:1000]))

    def close(self) -> None:
        self.conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def row_list(row: sqlite3.Row, col: str) -> list[str]:
    v = row[col]
    if not v:
        return []
    try:
        return list(json.loads(v))
    except (ValueError, TypeError):
        return [v]
