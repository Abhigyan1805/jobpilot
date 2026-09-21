import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobpilot.answers import AnswerBook
from jobpilot.applying.applier import Applier
from jobpilot.applying.base import EmailAdapter, build_adapter
from jobpilot.models import ApplicationPlan, GeneratedResume
from jobpilot.store import Store
from tests.helpers import mini_profile, posting, strong_match, test_config


class _FakeHttpResponse:
    status = 200

    def __init__(self, body: bytes = b"<html>ok</html>"):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class LinkOutSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.pdf = Path(self.tmp.name) / "resume.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake")
        self.answers = AnswerBook(
            answers={
                "name": "Abhigyan Sharma",
                "first_name": "Abhigyan",
                "last_name": "Sharma",
                "email": "abhigyan@example.com",
                "phone": "+91 9000000000",
                "github": "https://github.com/abhigyan",
                "linkedin": "https://linkedin.com/in/abhigyan",
            },
            profile=mini_profile(),
        )
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _plan(self, p):
        plan = ApplicationPlan(posting=p, match=strong_match())
        plan.resume = GeneratedResume(pdf_path=str(self.pdf))
        return plan

    def test_ats_board_is_routed_to_review_with_direct_link(self):
        adapter = build_adapter(self.cfg, self.answers)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            job_id="gh-1",
            description="Machine learning internship, January 2026 - June 2026. Python, RAG.",
            apply_url="https://boards.greenhouse.io/acme/jobs/123",
        )
        outcome = applier.process(self._plan(p))
        self.assertEqual(outcome.action, "review")
        self.assertFalse(self.store.has_submitted(p.stable_id))
        rows = self.store.list_review("pending")
        self.assertIn(p.stable_id, [r["stable_id"] for r in rows])
        packet = Path(rows[0]["packet_dir"])
        self.assertEqual(
            (packet / "apply_link.txt").read_text(encoding="utf-8").strip(),
            "https://boards.greenhouse.io/acme/jobs/123",
        )

    def test_html_apply_page_is_never_posted_or_recorded_submitted(self):
        adapter = build_adapter(self.cfg, self.answers)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            source="lever",
            job_id="lv-1",
            description="Machine learning internship, January 2026 - June 2026. Python, RAG.",
            apply_url="https://jobs.lever.co/spotify/abc/apply",
        )
        with mock.patch("urllib.request.urlopen", autospec=True) as urlopen:
            urlopen.return_value = _FakeHttpResponse()
            outcome = applier.process(self._plan(p))
        self.assertEqual(outcome.action, "review")
        urlopen.assert_not_called()
        self.assertFalse(self.store.has_submitted(p.stable_id))
        statuses = [
            row["status"]
            for row in self.store.iter_rows(
                "SELECT status FROM attempts WHERE stable_id = ?", [p.stable_id]
            )
        ]
        self.assertNotIn("submitted", statuses)
        self.assertNotIn("submitting", statuses)

    def test_unknown_adapter_value_is_rejected(self):
        self.cfg.apply.adapter = "emial"
        with self.assertRaises(ValueError):
            build_adapter(self.cfg, self.answers)

    def test_known_adapter_kinds_resolve_safely(self):
        self.cfg.apply.adapter = "auto"
        self.assertEqual(build_adapter(self.cfg, self.answers).name, "email")
        self.cfg.apply.adapter = "email"
        self.assertEqual(build_adapter(self.cfg, self.answers).name, "email")
        self.cfg.apply.adapter = "none"
        self.assertEqual(build_adapter(self.cfg, self.answers).name, "no_public_path")


class EmailRecipientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "resume.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake")
        self.cfg = test_config(
            Path(self.tmp.name),
            apply={"submission": {"smtp": {"host": "smtp.example.com"}, "email_allowlist": ["hr@acme.com"]}},
        )
        self.answers = AnswerBook(answers={"email": "me@example.com"}, profile=mini_profile())

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, p):
        plan = ApplicationPlan(posting=p, match=strong_match())
        plan.resume = GeneratedResume(pdf_path=str(self.pdf))
        return plan

    def _adapter(self):
        return EmailAdapter(self.cfg, self.answers)

    def test_free_text_address_is_never_used(self):
        p = posting(job_id="e-1", description="Send your resume to support@acme.com to apply.")
        ok, reason = self._adapter().can_submit(self._plan(p))
        self.assertFalse(ok)
        self.assertIn("authorized application email", reason)

    def test_structured_address_not_in_allowlist_is_refused(self):
        p = posting(job_id="e-2")
        p.apply_email = "random@acme.com"
        ok, reason = self._adapter().can_submit(self._plan(p))
        self.assertFalse(ok)
        self.assertIn("allowlist", reason)

    def test_structured_allowed_address_is_accepted(self):
        p = posting(job_id="e-3")
        p.apply_email = "hr@acme.com"
        ok, reason = self._adapter().can_submit(self._plan(p))
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
