import tempfile
import unittest
from pathlib import Path

from jobpilot.answers import AnswerBook
from jobpilot.applying.applier import Applier
from jobpilot.applying.base import SubmissionAdapter
from jobpilot.models import SubmissionResult
from jobpilot.store import Store
from tests.helpers import FakeAdapter, plan_for, posting, test_config


class RequiredFieldAdapter(SubmissionAdapter):
    name = "form"
    required_fields = ["work_authorization"]

    def __init__(self, config):
        super().__init__(config, AnswerBook(answers={}))
        self.calls = 0

    def submit(self, plan):
        self.calls += 1
        return SubmissionResult(status="submitted", detail="x", adapter=self.name)


class GuardrailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_missing_required_field_routes_to_review(self):
        adapter = RequiredFieldAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(posting(job_id="req-1"))
        outcome = applier.process(plan)
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "manual_required")
        self.assertEqual(adapter.calls, 0)
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(plan.posting.stable_id, queued)

    def test_linkedin_is_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(posting(source="linkedin", job_id="li-1"))
        outcome = applier.process(plan)
        self.assertEqual(outcome.status, "linkedin_review")
        self.assertEqual(adapter.calls, [])
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(plan.posting.stable_id, queued)

    def test_weak_match_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(posting(job_id="weak-1"), match=self._weak())
        outcome = applier.process(plan)
        self.assertEqual(outcome.status, "shortlist_review")
        self.assertEqual(adapter.calls, [])

    def test_dry_run_never_submits(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        outcome = applier.process(plan_for(posting(job_id="dry-1")), dry_run=True)
        self.assertEqual(outcome.status, "dry_run")
        self.assertEqual(adapter.calls, [])

    @staticmethod
    def _weak():
        from tests.helpers import strong_match

        m = strong_match(score=0.3)
        m.band = "shortlist"
        return m


if __name__ == "__main__":
    unittest.main()
