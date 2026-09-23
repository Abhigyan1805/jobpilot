"""Durable local store (SQLite) for postings, applications, attempts and the
review queue.

The store is the record of truth for deduplication and the daily cap: an attempt
is recorded *before* any submission is attempted, so a crash mid-submit cannot
cause a second application to the same posting.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jobpilot.models import ApplicationPlan, JobPosting, MatchResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    stable_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    job_id TEXT NOT NULL,
    company TEXT,
    title TEXT,
    url TEXT,
    apply_url TEXT,
    apply_email TEXT,
    location TEXT,
    employment_type TEXT,
    published_at TEXT,
    description TEXT,
    is_remote INTEGER,
    eligible INTEGER,
    window_label TEXT,
    window_confidence REAL,
    reject_reasons TEXT,
    score REAL,
    band TEXT,
    match_reasons TEXT,
    rubric TEXT,
    keyword_coverage TEXT,
    missing_keywords TEXT,
    seen_at TEXT,
    scored_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_postings_score ON postings(score);
CREATE INDEX IF NOT EXISTS idx_postings_eligible ON postings(eligible);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_id TEXT NOT NULL,
    company TEXT,
    title TEXT,
    url TEXT,
    apply_url TEXT,
    status TEXT NOT NULL,
    mode TEXT,
    score REAL,
    gaps TEXT,
    red_flags TEXT,
    adapter TEXT,
    review_reason TEXT,
    review_category TEXT,
    resume_tex TEXT,
    resume_pdf TEXT,
    resume_text TEXT,
    cover_tex TEXT,
    cover_pdf TEXT,
    cover_text TEXT,
    parseability_ok INTEGER,
    outcome TEXT,
    error TEXT,
    created_at TEXT,
    submitted_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_applications_stable ON applications(stable_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_id TEXT NOT NULL UNIQUE,
    source TEXT,
    company TEXT,
    title TEXT,
    url TEXT,
    apply_url TEXT,
    score REAL,
    reasons TEXT,
    gaps TEXT,
    matched_keywords TEXT,
    missing_keywords TEXT,
    resume_pdf TEXT,
    cover_pdf TEXT,
    packet_dir TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_id TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    day TEXT NOT NULL,
    adapter TEXT,
    status TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_stable ON attempts(stable_id);
CREATE INDEX IF NOT EXISTS idx_attempts_day ON attempts(day);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    mode TEXT,
    stats TEXT
);
"""


# Review routes caused by a transient condition. Such a posting may be
# auto-applied once the condition clears (the daily cap window resets, a
# submission channel/recipient is configured, or auto-apply is re-enabled), so
# these categories must not dedupe. The category is stored in
# ``applications.review_category``; ``review_reason`` holds the human-readable
# detail. Categories that encode a human decision (``human_*``), an uncertain
# window/match, or a manual-only source stay blocking.
TRANSIENT_REVIEW_REASONS = frozenset({"capped", "no_channel", "config"})


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(applications)")}
        if "review_reason" not in cols:
            self.conn.execute("ALTER TABLE applications ADD COLUMN review_reason TEXT")
        if "review_category" not in cols:
            self.conn.execute("ALTER TABLE applications ADD COLUMN review_category TEXT")
            # Older rows stored only the guard category in review_reason; copy it
            # across so transient-route detection keeps working after upgrade.
            self.conn.execute(
                "UPDATE applications SET review_category = review_reason "
                "WHERE review_category IS NULL"
            )
        rq_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(review_queue)")}
        if "matched_keywords" not in rq_cols:
            self.conn.execute("ALTER TABLE review_queue ADD COLUMN matched_keywords TEXT")
        posting_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(postings)")}
        if "apply_email" not in posting_cols:
            self.conn.execute("ALTER TABLE postings ADD COLUMN apply_email TEXT")

    def close(self) -> None:
        self.conn.close()

    # ---------------------------------------------------------------- postings
    def upsert_posting(
        self,
        posting: JobPosting,
        *,
        eligible: bool | None = None,
        window_label: str = "",
        window_confidence: float | None = None,
        reject_reasons: list[str] | None = None,
    ) -> bool:
        """Insert or refresh a posting. Returns True when newly inserted."""
        now = utcnow()
        exists = self.get_posting(posting.stable_id) is not None
        self.conn.execute(
            """
            INSERT INTO postings (
                stable_id, source, job_id, company, title, url, apply_url, apply_email,
                location, employment_type, published_at, description, is_remote, eligible,
                window_label, window_confidence, reject_reasons, seen_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(stable_id) DO UPDATE SET
                company=excluded.company,
                title=excluded.title,
                url=excluded.url,
                apply_url=excluded.apply_url,
                apply_email=excluded.apply_email,
                location=excluded.location,
                employment_type=excluded.employment_type,
                published_at=excluded.published_at,
                description=excluded.description,
                is_remote=excluded.is_remote,
                eligible=COALESCE(excluded.eligible, postings.eligible),
                window_label=excluded.window_label,
                window_confidence=excluded.window_confidence,
                reject_reasons=COALESCE(excluded.reject_reasons, postings.reject_reasons),
                updated_at=excluded.updated_at
            """,
            (
                posting.stable_id,
                posting.source,
                posting.job_id,
                posting.company,
                posting.title,
                posting.url,
                posting.apply_url or posting.url,
                posting.apply_email,
                posting.location,
                posting.employment_type,
                posting.published_at,
                posting.description,
                None if posting.is_remote is None else int(posting.is_remote),
                None if eligible is None else int(eligible),
                window_label,
                window_confidence,
                json.dumps(reject_reasons) if reject_reasons is not None else None,
                now,
                now,
            ),
        )
        self.conn.commit()
        return not exists

    def get_posting(self, stable_id: str) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM postings WHERE stable_id = ?", (stable_id,))
        return cur.fetchone()

    def save_match(self, stable_id: str, match: MatchResult, *, eligible: bool, reject_reasons: list[str]) -> None:
        d = match.to_dict()
        self.conn.execute(
            """
            UPDATE postings SET
                eligible=?, reject_reasons=?, score=?, band=?, match_reasons=?,
                rubric=?, keyword_coverage=?, missing_keywords=?, scored_at=?, updated_at=?
            WHERE stable_id=?
            """,
            (
                int(eligible),
                json.dumps(reject_reasons),
                match.score,
                match.band,
                json.dumps(match.reasons),
                json.dumps(match.rubric),
                json.dumps(d["coverage"]),
                json.dumps(match.missing_keywords),
                utcnow(),
                utcnow(),
                stable_id,
            ),
        )
        self.conn.commit()

    def list_postings(self, *, eligible: bool | None = None, min_score: float | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM postings"
        clauses: list[str] = []
        params: list[Any] = []
        if eligible is not None:
            clauses.append("eligible = ?")
            params.append(int(eligible))
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(min_score)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY score DESC NULLS LAST"
        return list(self.conn.execute(sql, params).fetchall())

    # ------------------------------------------------------------ applications
    def submitted_or_attempted(self, stable_id: str) -> sqlite3.Row | None:
        """Return the record that must block another submission, if any.

        Only an in-flight submit, a completed submit, or a human-in-the-loop
        review route blocks. A transient review route (daily cap reached, or no
        submission channel configured yet) does not block, so the posting can be
        auto-applied once the condition clears; a failed attempt does not block
        either, so it can be retried.
        """
        rows = self.conn.execute(
            "SELECT * FROM applications WHERE stable_id = ? ORDER BY id DESC",
            (stable_id,),
        ).fetchall()
        for row in rows:
            status = row["status"]
            if status in ("submitting", "submitted"):
                return row
            if status == "manual_required":
                category = row["review_category"] or row["review_reason"] or ""
                if category in TRANSIENT_REVIEW_REASONS:
                    continue
                return row
        return None

    def has_submitted(self, stable_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM applications WHERE stable_id = ? AND status = 'submitted' LIMIT 1",
            (stable_id,),
        )
        return cur.fetchone() is not None

    def create_application(
        self,
        plan: ApplicationPlan,
        *,
        status: str,
        mode: str,
        adapter: str = "",
        review_reason: str = "",
        review_category: str = "",
    ) -> int:
        now = utcnow()
        p, m = plan.posting, plan.match
        cur = self.conn.execute(
            """
            INSERT INTO applications (
                stable_id, company, title, url, apply_url, status, mode, score, gaps,
                red_flags, adapter, review_reason, review_category, resume_tex, resume_pdf,
                resume_text, cover_tex, cover_pdf, cover_text, parseability_ok, created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                p.stable_id,
                p.company,
                p.title,
                p.url,
                p.apply_url or p.url,
                status,
                mode,
                m.score,
                json.dumps(plan.gaps),
                json.dumps(plan.red_flags),
                adapter,
                review_reason,
                review_category,
                plan.resume.tex_path if plan.resume else "",
                plan.resume.pdf_path if plan.resume else "",
                plan.resume.text if plan.resume else "",
                plan.cover.tex_path if plan.cover else "",
                plan.cover.pdf_path if plan.cover else "",
                plan.cover.text if plan.cover else "",
                int(plan.resume.parseability_ok) if plan.resume else None,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_application(self, app_id: int, *, status: str, outcome: str = "", error: str = "") -> None:
        submitted = utcnow() if status == "submitted" else None
        self.conn.execute(
            """
            UPDATE applications SET status=?, outcome=?, error=?, updated_at=?,
                submitted_at=COALESCE(?, submitted_at)
            WHERE id=?
            """,
            (status, outcome, error, utcnow(), submitted, app_id),
        )
        if status == "submitted":
            row = self.conn.execute(
                "SELECT stable_id FROM applications WHERE id = ?", (app_id,)
            ).fetchone()
            if row is not None:
                self.conn.execute(
                    "UPDATE review_queue SET status='superseded', decided_at=? "
                    "WHERE stable_id=? AND status='pending'",
                    (utcnow(), row["stable_id"]),
                )
        self.conn.commit()

    # ----------------------------------------------------------------- attempts
    def record_attempt(self, stable_id: str, *, adapter: str, status: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO attempts (stable_id, attempted_at, day, adapter, status, detail) VALUES (?,?,?,?,?,?)",
            (stable_id, utcnow(), today(), adapter, status, detail),
        )
        self.conn.commit()

    def attempts_today(self) -> int:
        """Distinct postings actually attempted today (excludes dry runs, caps, reviews)."""
        cur = self.conn.execute(
            "SELECT COUNT(DISTINCT stable_id) AS n FROM attempts "
            "WHERE day = ? AND status IN ('submitting','submitted','failed')",
            (today(),),
        )
        return int(cur.fetchone()["n"])

    # -------------------------------------------------------------- review queue
    def enqueue_review(self, plan: ApplicationPlan, *, packet_dir: str = "") -> None:
        now = utcnow()
        self.conn.execute(
            """
            INSERT INTO review_queue (
                stable_id, source, company, title, url, apply_url, score, reasons,
                gaps, matched_keywords, missing_keywords, resume_pdf, cover_pdf, packet_dir,
                status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending', ?)
            ON CONFLICT(stable_id) DO UPDATE SET
                score=excluded.score,
                reasons=excluded.reasons,
                gaps=excluded.gaps,
                matched_keywords=excluded.matched_keywords,
                missing_keywords=excluded.missing_keywords,
                resume_pdf=excluded.resume_pdf,
                cover_pdf=excluded.cover_pdf,
                packet_dir=excluded.packet_dir
            """,
            (
                plan.posting.stable_id,
                plan.posting.source,
                plan.posting.company,
                plan.posting.title,
                plan.posting.url,
                plan.posting.apply_url or plan.posting.url,
                plan.match.score,
                json.dumps(plan.match.reasons),
                json.dumps(plan.gaps),
                json.dumps(list(plan.match.coverage.matched)),
                json.dumps(plan.missing_keywords),
                plan.resume.pdf_path if plan.resume else "",
                plan.cover.pdf_path if plan.cover else "",
                packet_dir,
                now,
            ),
        )
        self.conn.commit()

    def list_review(self, status: str = "pending") -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM review_queue WHERE status = ? ORDER BY score DESC", (status,)
            ).fetchall()
        )

    def get_review(self, review_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM review_queue WHERE id = ?", (review_id,)).fetchone()

    def decide_review(self, review_id: int, status: str) -> sqlite3.Row | None:
        row = self.get_review(review_id)
        if row is None:
            return None
        self.conn.execute(
            "UPDATE review_queue SET status=?, decided_at=? WHERE id=?",
            (status, utcnow(), review_id),
        )
        # A human decision closes the route for good: the posting must never be
        # auto-submitted afterwards, even if the original route was transient.
        # The category records the decision; review_reason keeps the detail.
        self.conn.execute(
            "UPDATE applications SET review_category=?, updated_at=? "
            "WHERE stable_id=? AND status='manual_required'",
            (f"human_{status}", utcnow(), row["stable_id"]),
        )
        self.conn.commit()
        return self.get_review(review_id)

    # --------------------------------------------------------------------- runs
    def start_run(self, mode: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, mode) VALUES (?, ?)", (utcnow(), mode)
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, stats: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, stats=? WHERE id=?",
            (utcnow(), json.dumps(stats), run_id),
        )
        self.conn.commit()

    def iter_rows(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, tuple(params)).fetchall())
