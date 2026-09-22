import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobpilot.answers import AnswerBook
from jobpilot.applying.applier import Applier
from jobpilot.applying.base import build_adapter
from jobpilot.models import GeneratedResume, SubmissionResult
from jobpilot.store import Store
from tests.helpers import FakeAdapter, mini_profile, plan_for, posting, test_config

IN_WINDOW = "Machine learning internship, January 2026 - June 2026. Python, RAG."


def _next_day(store: Store) -> None:
    store.conn.execute("UPDATE attempts SET day = '2000-01-01'")
    store.conn.commit()


class ReviewRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_daily_cap_review_reopens_next_day(self):
        cfg = test_config(Path(self.tmp.name), apply={"daily_cap": 1})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        first = plan_for(posting(job_id="cap-reopen-1", description=IN_WINDOW))
        capped = plan_for(posting(job_id="cap-reopen-2", description=IN_WINDOW))

        self.assertEqual(applier.process(first).status, "submitted")
        self.assertEqual(applier.process(capped).status, "capped")

        _next_day(self.store)
        self.assertEqual(applier.process(capped).status, "submitted")
        self.assertTrue(self.store.has_submitted(capped.posting.stable_id))
        self.assertNotIn(
            capped.posting.stable_id,
            [r["stable_id"] for r in self.store.list_review("pending")],
        )

    def test_human_approved_review_stays_closed(self):
        cfg = test_config(Path(self.tmp.name), apply={"daily_cap": 1})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        applier.process(plan_for(posting(job_id="cap-human-1", description=IN_WINDOW)))
        capped = plan_for(posting(job_id="cap-human-2", description=IN_WINDOW))
        applier.process(capped)

        review = self.store.list_review("pending")[0]
        self.store.decide_review(review["id"], "approved")

        _next_day(self.store)
        retry = applier.process(capped)
        self.assertEqual(retry.status, "duplicate")
        self.assertFalse(self.store.has_submitted(capped.posting.stable_id))

    def test_apply_disabled_review_reopens_once_enabled(self):
        cfg = test_config(Path(self.tmp.name), apply={"enabled": False})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        p = posting(job_id="cfg-enabled-1", description=IN_WINDOW)

        first = applier.process(plan_for(p))
        self.assertEqual(first.action, "review")
        self.assertEqual(first.reason, "auto-apply disabled by config")
        self.assertIn(p.stable_id, [r["stable_id"] for r in self.store.list_review("pending")])

        cfg.apply.enabled = True
        second = applier.process(plan_for(p))
        self.assertEqual(second.status, "submitted")
        self.assertTrue(self.store.has_submitted(p.stable_id))

    def test_auto_apply_disabled_review_reopens_once_reenabled(self):
        cfg = test_config(Path(self.tmp.name), apply={"auto_apply_strong": False})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        p = posting(job_id="cfg-strong-1", description=IN_WINDOW)

        first = applier.process(plan_for(p))
        self.assertEqual(first.action, "review")
        self.assertIn(p.stable_id, [r["stable_id"] for r in self.store.list_review("pending")])

        cfg.apply.auto_apply_strong = True
        second = applier.process(plan_for(p))
        self.assertEqual(second.status, "submitted")
        self.assertTrue(self.store.has_submitted(p.stable_id))

    def test_no_channel_review_reopens_once_recipient_configured(self):
        cfg = test_config(Path(self.tmp.name))
        answers = AnswerBook(answers={"email": "me@example.com"}, profile=mini_profile())
        adapter = build_adapter(cfg, answers)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)

        p = posting(job_id="nochan-1", description=IN_WINDOW)
        plan = plan_for(p)
        pdf = Path(self.tmp.name) / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        plan.resume = GeneratedResume(pdf_path=str(pdf))

        first = applier.process(plan)
        self.assertEqual(first.status, "manual_required")
        self.assertIn(p.stable_id, [r["stable_id"] for r in self.store.list_review("pending")])

        p.apply_email = "hr@acme.com"
        cfg.apply.submission = {
            "smtp": {"host": "smtp.example.com"},
            "email_allowlist": ["hr@acme.com"],
        }
        adapter.submit = mock.Mock(
            return_value=SubmissionResult(status="submitted", detail="emailed", adapter=adapter.name)
        )

        second = applier.process(plan)
        self.assertEqual(second.status, "submitted")
        adapter.submit.assert_called_once()
        self.assertTrue(self.store.has_submitted(p.stable_id))


if __name__ == "__main__":
    unittest.main()
