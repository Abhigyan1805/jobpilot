import tempfile
import unittest
from pathlib import Path

from jobpilot.applying.applier import Applier
from jobpilot.store import Store
from tests.helpers import FakeAdapter, plan_for, posting, test_config

IN_WINDOW = (
    "Machine learning internship, January 2026 - June 2026. Python, RAG. "
    "Stipend: ₹40,000/month."
)


class DailyCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name), apply={"daily_cap": 1})
        self.store = Store(":memory:")
        self.adapter = FakeAdapter(self.cfg)
        self.applier = Applier(self.store, self.cfg, self.adapter, self.cfg.output.dir)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_cap_blocks_second_submission(self):
        first = self.applier.process(plan_for(posting(job_id="cap-1", description=IN_WINDOW)))
        second = self.applier.process(plan_for(posting(job_id="cap-2", description=IN_WINDOW)))
        self.assertEqual(first.status, "submitted")
        self.assertEqual(second.status, "capped")
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.store.attempts_today(), 1)

    def test_capped_posting_is_queued_for_review(self):
        self.applier.process(plan_for(posting(job_id="cap-3", description=IN_WINDOW)))
        second_plan = plan_for(posting(job_id="cap-4", description=IN_WINDOW))
        self.applier.process(second_plan)
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(second_plan.posting.stable_id, queued)


if __name__ == "__main__":
    unittest.main()
