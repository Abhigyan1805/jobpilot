import tempfile
import unittest
from pathlib import Path

from jobpilot.answers import AnswerBook
from jobpilot.applying.applier import Applier
from jobpilot.applying.base import SubmissionAdapter
from jobpilot.models import SubmissionResult
from jobpilot.store import Store
from tests.helpers import FakeAdapter, plan_for, posting, test_config

# A description with a confirmed Jan-Jun window and a stated stipend, so these
# guardrail tests exercise the gate under test rather than the unknown-window or
# unstated-stipend review gates.
IN_WINDOW = (
    "Machine learning internship, January 2026 - June 2026. Python, RAG. "
    "Stipend: ₹40,000/month."
)
IN_WINDOW_NO_STIPEND = "Machine learning internship, January 2026 - June 2026. Python, RAG."


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
        plan = plan_for(posting(job_id="req-1", description=IN_WINDOW))
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
        plan = plan_for(posting(job_id="weak-1", description=IN_WINDOW), match=self._weak())
        outcome = applier.process(plan)
        self.assertEqual(outcome.status, "shortlist_review")
        self.assertEqual(adapter.calls, [])

    def test_dry_run_never_submits(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        outcome = applier.process(plan_for(posting(job_id="dry-1", description=IN_WINDOW)), dry_run=True)
        self.assertEqual(outcome.status, "dry_run")
        self.assertEqual(adapter.calls, [])

    def test_requires_review_plan_is_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(posting(job_id="req-2"))
        plan.requires_review = True
        plan.review_reason = "parseability check failed: missing section"
        outcome = applier.process(plan)
        self.assertEqual(outcome.status, "requires_review")
        self.assertEqual(adapter.calls, [])
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(plan.posting.stable_id, queued)

    def test_detailed_review_reason_is_persisted_with_its_category(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(posting(job_id="reason-1"))
        plan.requires_review = True
        plan.review_reason = "parseability check failed: keyword survival 0% below 50%"

        applier.process(plan)

        row = self.store.conn.execute(
            "SELECT review_reason, review_category FROM applications WHERE stable_id = ?",
            (plan.posting.stable_id,),
        ).fetchone()
        self.assertEqual(
            row["review_reason"], "parseability check failed: keyword survival 0% below 50%"
        )
        self.assertEqual(row["review_category"], "generation")

    def test_unknown_window_strong_match_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(posting(job_id="unknown-window-1"))
        outcome = applier.process(plan)
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "window_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(plan.posting.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(plan.posting.stable_id, queued)

    def test_unknown_window_allowed_config_may_auto_submit(self):
        cfg = test_config(Path(self.tmp.name), filt={"allow_unknown_window": True})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        plan = plan_for(
            posting(
                job_id="unknown-window-2",
                description="Machine learning internship. Python, RAG. Stipend: ₹40,000/month.",
            )
        )
        outcome = applier.process(plan)
        self.assertEqual(outcome.status, "submitted")
        self.assertEqual(adapter.calls, [plan.posting.stable_id])

    def test_unstated_stipend_is_review_only_never_auto_applied(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(job_id="stipend-unstated-1", description=IN_WINDOW_NO_STIPEND)
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        self.assertIn(p.stable_id, [r["stable_id"] for r in self.store.list_review("pending")])

    def test_confirmed_at_floor_stipend_still_auto_applies(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(job_id="stipend-confirmed-1", description=IN_WINDOW)
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.status, "submitted")
        self.assertEqual(adapter.calls, [p.stable_id])

    def test_deadline_iso_range_is_not_a_verified_window_for_auto_apply(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(
            posting(
                job_id="deadline-range-1",
                description=(
                    "Machine learning internship. Applications accepted 2025-01-05 through "
                    "2025-05-30. Python, RAG."
                ),
            )
        )
        outcome = applier.process(plan)
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "window_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(plan.posting.stable_id))

    def test_deadline_iso_range_overlapping_the_window_never_auto_applies(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(
            posting(
                job_id="deadline-range-2",
                title="Machine Learning Intern",
                employment_type="Internship",
                description="Deadline: 2025-02-01 through 2025-03-15.",
            )
        )
        outcome = applier.process(plan)
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "window_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(plan.posting.stable_id))

    def test_application_period_with_start_verb_never_auto_applies(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        plan = plan_for(
            posting(
                job_id="application-period-verb-1",
                description=(
                    "Machine Learning Intern. Application period begins 2025-01-10 to "
                    "2025-05-30. Python, RAG."
                ),
            )
        )
        outcome = applier.process(plan)
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "window_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(plan.posting.stable_id))

    def test_remote_us_only_in_description_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-loc-1",
            location="Remote",
            is_remote=True,
            description=IN_WINDOW + " Candidates must be located in the United States.",
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_security_clearance_only_in_description_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-loc-clearance-1",
            location="Remote",
            is_remote=True,
            description=IN_WINDOW + " Must be eligible for a security clearance.",
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_global_tagged_us_restriction_only_in_description_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-loc-global-1",
            location="Remote - Worldwide",
            is_remote=True,
            description=IN_WINDOW + " Candidates must be located in the United States.",
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_city_only_foreign_location_with_india_mention_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-loc-city-1",
            location="New York, NY",
            is_remote=None,
            description=IN_WINDOW + " Our global hubs include Bengaluru, India.",
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_fulltime_role_mentioning_interns_never_auto_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-ft-1",
            title="Software Engineer",
            employment_type="",
            location="Remote - Worldwide",
            is_remote=True,
            description=(
                "This is a full-time role. You will mentor interns and run our "
                "internship program. " + IN_WINDOW
            ),
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_genuine_internship_fulltime_conversion_routed_to_review(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-ft-conv-1",
            title="Machine Learning Intern",
            location="Bengaluru, India",
            description=(
                IN_WINDOW + " Strong performers may receive an opportunity for "
                "full-time conversion."
            ),
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_intern_title_tagged_fulltime_routed_to_review(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="filter-ft-tag-1",
            title="Machine Learning Intern",
            employment_type="FullTime",
            location="Bengaluru, India",
            description=IN_WINDOW,
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))
        queued = [r["stable_id"] for r in self.store.list_review("pending")]
        self.assertIn(p.stable_id, queued)

    def test_auto_apply_strong_disabled_routes_to_review(self):
        cfg = test_config(Path(self.tmp.name), apply={"auto_apply_strong": False})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        outcome = applier.process(plan_for(posting(job_id="no-auto-1", description=IN_WINDOW)))
        self.assertEqual(outcome.action, "review")
        self.assertIn("auto_apply_strong", outcome.reason)
        self.assertEqual(adapter.calls, [])

    def test_apply_disabled_routes_to_review(self):
        cfg = test_config(Path(self.tmp.name), apply={"enabled": False})
        adapter = FakeAdapter(cfg)
        applier = Applier(self.store, cfg, adapter, cfg.output.dir)
        outcome = applier.process(plan_for(posting(job_id="disabled-1", description=IN_WINDOW)))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(adapter.calls, [])

    @staticmethod
    def _weak():
        from tests.helpers import strong_match

        m = strong_match(score=0.3)
        m.band = "shortlist"
        return m


if __name__ == "__main__":
    unittest.main()
