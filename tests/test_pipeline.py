import unittest

from jobpilot.answers import AnswerBook
from jobpilot.applying.base import build_adapter
from jobpilot.filtering import filter_posting
from jobpilot.models import GeneratedResume
from jobpilot.pipeline import _postings_from_store
from jobpilot.store import Store
from tests.helpers import mini_profile, plan_for, posting, test_config

IN_WINDOW = "Machine learning internship, January 2026 - June 2026. Python, RAG, LLMs, evaluation."


class StoreReloadTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.cfg = test_config()

    def tearDown(self):
        self.store.close()

    def test_reload_restores_is_remote_and_preserves_eligibility(self):
        original = posting(
            job_id="local-remote-1",
            location="",
            is_remote=True,
            description=IN_WINDOW,
        )
        original_filter = filter_posting(original, self.cfg.filter)
        self.assertTrue(original_filter.eligible)

        self.store.upsert_posting(
            original,
            eligible=original_filter.eligible,
            window_label=original_filter.window_label,
            window_confidence=original_filter.window_confidence,
            reject_reasons=original_filter.reject_reasons,
        )

        reloaded = _postings_from_store(self.store)
        self.assertEqual(len(reloaded), 1)
        self.assertIs(reloaded[0].is_remote, True)

        reloaded_filter = filter_posting(reloaded[0], self.cfg.filter)
        self.assertTrue(reloaded_filter.eligible)

    def test_reload_preserves_known_remote_false(self):
        original = posting(
            job_id="local-onsite-1",
            location="Bengaluru, India",
            is_remote=False,
            description=IN_WINDOW,
        )
        self.store.upsert_posting(original)
        reloaded = _postings_from_store(self.store)
        self.assertIs(reloaded[0].is_remote, False)

    def test_reload_restores_apply_email_so_email_channel_can_submit(self):
        original = posting(
            job_id="local-email-1",
            location="Bengaluru, India",
            description=IN_WINDOW,
            apply_email="hr@acme.com",
        )
        self.store.upsert_posting(original)

        reloaded = _postings_from_store(self.store)
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].apply_email, "hr@acme.com")

        cfg = test_config()
        cfg.apply.submission = {"smtp": {"host": "smtp.example.com"}}
        answers = AnswerBook(answers={"email": "me@example.com"}, profile=mini_profile())
        adapter = build_adapter(cfg, answers)
        plan = plan_for(reloaded[0])
        plan.resume = GeneratedResume(pdf_path="/tmp/resume.pdf")
        can_submit, reason = adapter.can_submit(plan)
        self.assertTrue(can_submit, reason)


if __name__ == "__main__":
    unittest.main()
