"""Tests for application archiving, outcomes, follow-ups and the stale sweep."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jobpilot.applying.applier import Applier
from jobpilot.archive import archive_application
from jobpilot.cli import main
from jobpilot.lifecycle import (
    candidate_for,
    followup_candidates,
    followup_template,
    is_final,
    quiet_days,
    stale_candidates,
)
from jobpilot.models import ApplicationPlan, GeneratedResume
from jobpilot.store import Store
from tests.helpers import FakeAdapter, posting, strong_match, test_config

IN_WINDOW = "Machine learning internship, January 2026 - June 2026. Python, RAG."
TODAY = date(2026, 3, 10)


def _insert_application(
    store,
    stable_id,
    *,
    status="submitted",
    outcome=None,
    submitted_at="2026-01-01T00:00:00+00:00",
    updated_at="2026-01-01T00:00:00+00:00",
    last_followup_at=None,
    reminders=0,
    resume_pdf="",
    cover_pdf="",
    resume_tex="",
    cover_tex="",
):
    cur = store.conn.execute(
        """
        INSERT INTO applications (
            stable_id, company, title, status, outcome, submitted_at, updated_at,
            last_followup_at, reminders, gaps, resume_pdf, cover_pdf, resume_tex, cover_tex
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            stable_id,
            "Acme",
            "Machine Learning Intern",
            status,
            outcome,
            submitted_at,
            updated_at,
            last_followup_at,
            reminders,
            json.dumps([]),
            resume_pdf,
            cover_pdf,
            resume_tex,
            cover_tex,
        ),
    )
    store.conn.commit()
    return int(cur.lastrowid)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.store = Store(":memory:")
        self.pdf = Path(self.tmp.name) / "resume.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake")
        self.cover = Path(self.tmp.name) / "cover.pdf"
        self.cover.write_bytes(b"%PDF-1.4 cover")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _archive(self):
        self.store.upsert_posting(posting(job_id="arch-1"))
        app_id = _insert_application(
            self.store,
            "greenhouse:arch-1",
            resume_pdf=str(self.pdf),
            cover_pdf=str(self.cover),
        )
        row = self.store.get_application(app_id)
        return archive_application(self.store, self.cfg, row)

    def test_archives_materials_and_posting_text(self):
        base = Path(self._archive())
        self.assertTrue((base / "resume.pdf").exists())
        self.assertTrue((base / "cover_letter.pdf").exists())
        self.assertTrue((base / "job_posting.md").exists())
        self.assertTrue((base / "outcome.md").exists())
        self.assertIn("Machine Learning Intern", (base / "job_posting.md").read_text(encoding="utf-8"))
        row = self.store.latest_application("greenhouse:arch-1")
        self.assertEqual(row["archive_dir"], str(base))

    def test_existing_archived_material_is_never_overwritten(self):
        base = Path(self._archive())
        sentinel = base / "resume.pdf"
        sentinel.write_bytes(b"the version actually sent")
        # Re-run with a fresh draft on disk.
        self.pdf.write_bytes(b"a fresher draft")
        row = self.store.latest_application("greenhouse:arch-1")
        archive_application(self.store, self.cfg, row)
        self.assertEqual(sentinel.read_bytes(), b"the version actually sent")

    def test_auto_submit_archives(self):
        plan = ApplicationPlan(posting=posting(job_id="auto-arch-1", description=IN_WINDOW), match=strong_match())
        plan.resume = GeneratedResume(pdf_path=str(self.pdf))
        applier = Applier(self.store, self.cfg, FakeAdapter(self.cfg), self.cfg.output.dir)
        outcome = applier.process(plan)
        self.assertEqual(outcome.status, "submitted")
        row = self.store.latest_application(plan.posting.stable_id)
        self.assertTrue(row["archive_dir"])
        self.assertTrue((Path(row["archive_dir"]) / "resume.pdf").exists())


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_final_and_open(self):
        self.assertTrue(is_final("hired"))
        self.assertTrue(is_final("no_response"))
        self.assertFalse(is_final("interview"))
        self.assertFalse(is_final(""))
        self.assertFalse(is_final(None))

    def test_set_outcome_appends_note_and_updates(self):
        _insert_application(self.store, "o-1")
        self.store.set_outcome("o-1", "interview", note="phone screen booked")
        row = self.store.latest_application("o-1")
        self.assertEqual(row["outcome"], "interview")
        self.assertIn("phone screen booked", row["notes"])


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_quiet_application_is_a_candidate(self):
        _insert_application(
            self.store, "f-1", submitted_at="2026-02-20T00:00:00+00:00", updated_at="2026-02-20T00:00:00+00:00"
        )
        candidates = followup_candidates(self.store, days=10, max_reminders=2, today=TODAY)
        self.assertEqual([c.stable_id for c in candidates], ["f-1"])
        self.assertEqual(candidates[0].quiet_days, 18)

    def test_two_reminders_ends_the_chase(self):
        _insert_application(
            self.store,
            "f-2",
            submitted_at="2026-02-20T00:00:00+00:00",
            updated_at="2026-02-20T00:00:00+00:00",
            reminders=2,
        )
        self.assertEqual(followup_candidates(self.store, days=10, max_reminders=2, today=TODAY), [])

    def test_final_outcome_is_not_chased(self):
        _insert_application(
            self.store,
            "f-3",
            outcome="rejected",
            submitted_at="2026-02-20T00:00:00+00:00",
            updated_at="2026-02-20T00:00:00+00:00",
        )
        self.assertEqual(followup_candidates(self.store, days=10, max_reminders=2, today=TODAY), [])

    def test_recent_application_is_not_chased(self):
        _insert_application(
            self.store, "f-4", submitted_at="2026-03-08T00:00:00+00:00", updated_at="2026-03-08T00:00:00+00:00"
        )
        self.assertEqual(followup_candidates(self.store, days=10, max_reminders=2, today=TODAY), [])

    def test_followup_resets_the_quiet_clock(self):
        _insert_application(
            self.store, "f-5", submitted_at="2026-02-01T00:00:00+00:00", updated_at="2026-02-01T00:00:00+00:00"
        )
        self.store.record_followup("f-5", note="follow-up sent")
        row = self.store.latest_application("f-5")
        self.assertEqual(int(row["reminders"]), 1)
        self.assertIsNotNone(row["last_followup_at"])
        # The clock resets to now (the record_followup timestamp is real "now").
        self.assertEqual(quiet_days(row), 0)

    def test_template_names_role_and_company_without_new_claims(self):
        _insert_application(
            self.store, "f-6", submitted_at="2026-02-20T00:00:00+00:00", updated_at="2026-02-20T00:00:00+00:00"
        )
        candidate = candidate_for(self.store, "f-6", today=TODAY)
        text = followup_template(candidate)
        self.assertIn("Machine Learning Intern", text)
        self.assertIn("Acme", text)


class StaleSweepTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_only_long_quiet_open_applications(self):
        _insert_application(
            self.store, "s-1", submitted_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00"
        )
        _insert_application(
            self.store, "s-2", outcome="rejected", submitted_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        candidates = stale_candidates(self.store, days=60, today=TODAY)
        self.assertEqual([c.stable_id for c in candidates], ["s-1"])


class CliLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "jobpilot.db"
        self.config_path = Path(self.tmp.name) / "config.toml"
        self.config_path.write_text(
            f"[output]\ndatabase = '{self.db}'\n[lifecycle]\nfollowup_days = 10\nstale_days = 60\n",
            encoding="utf-8",
        )
        self.store = Store(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_outcome_command_records_status(self):
        _insert_application(self.store, "cli-1", updated_at="2026-01-01T00:00:00+00:00")
        rc = main(["--config", str(self.config_path), "outcome", "cli-1", "--status", "offer"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.latest_application("cli-1")["outcome"], "offer")

    def test_outcome_command_rejects_unknown_status(self):
        _insert_application(self.store, "cli-2")
        rc = main(["--config", str(self.config_path), "outcome", "cli-2", "--status", "bogus"])
        self.assertEqual(rc, 2)

    def test_stale_write_marks_no_response(self):
        _insert_application(
            self.store, "cli-3", submitted_at="2025-01-01T00:00:00+00:00", updated_at="2025-01-01T00:00:00+00:00"
        )
        rc = main(["--config", str(self.config_path), "stale", "--write"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.latest_application("cli-3")["outcome"], "no_response")

    def test_followup_record_without_an_application_fails(self):
        self.store.upsert_posting(posting(job_id="cli-4"))
        rc = main(["--config", str(self.config_path), "followups", "--record", "greenhouse:cli-4"])
        self.assertEqual(rc, 1)
        self.assertIsNone(self.store.latest_application("greenhouse:cli-4"))

    def test_followup_record_logs_the_reminder(self):
        _insert_application(self.store, "cli-5")
        rc = main(["--config", str(self.config_path), "followups", "--record", "cli-5"])
        self.assertEqual(rc, 0)
        self.assertEqual(int(self.store.latest_application("cli-5")["reminders"]), 1)


if __name__ == "__main__":
    unittest.main()
