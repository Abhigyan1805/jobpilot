import tempfile
import unittest
from pathlib import Path

from jobpilot.applying.applier import Applier
from jobpilot.store import Store
from tests.helpers import FakeAdapter, plan_for, posting, test_config

IN_WINDOW = "Machine learning internship, January 2026 - June 2026. Python, RAG."


class DedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.store = Store(":memory:")
        self.adapter = FakeAdapter(self.cfg)
        self.applier = Applier(self.store, self.cfg, self.adapter, self.cfg.output.dir)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_same_posting_is_submitted_only_once(self):
        plan = plan_for(posting(job_id="dup-1", description=IN_WINDOW))
        first = self.applier.process(plan)
        second = self.applier.process(plan)
        self.assertEqual(first.status, "submitted")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertTrue(self.store.has_submitted(plan.posting.stable_id))

    def test_attempt_recorded_before_submission(self):
        plan = plan_for(posting(job_id="dup-2", description=IN_WINDOW))
        self.applier.process(plan)
        rows = self.store.iter_rows("SELECT status FROM attempts WHERE stable_id = ?", [plan.posting.stable_id])
        statuses = [r["status"] for r in rows]
        self.assertIn("submitting", statuses)
        self.assertIn("submitted", statuses)

    def test_different_postings_both_submitted(self):
        self.applier.process(plan_for(posting(job_id="a", description=IN_WINDOW)))
        self.applier.process(plan_for(posting(job_id="b", description=IN_WINDOW)))
        self.assertEqual(len(self.adapter.calls), 2)


if __name__ == "__main__":
    unittest.main()
