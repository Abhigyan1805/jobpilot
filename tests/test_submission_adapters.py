import tempfile
import unittest
from pathlib import Path

from jobpilot.answers import AnswerBook
from jobpilot.applying.applier import Applier
from jobpilot.applying.ats import AtsAdapter
from jobpilot.applying.base import EmailAdapter, build_adapter
from jobpilot.models import ApplicationPlan, GeneratedResume
from jobpilot.store import Store
from tests.helpers import mini_profile, posting, strong_match, test_config


class FakeTransport:
    def __init__(self, status: int = 200, body: str = "ok"):
        self.status = status
        self.body = body
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url, fields, files):
        self.calls.append((url, fields, files))
        return self.status, self.body


class AtsSubmissionTests(unittest.TestCase):
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

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, p):
        plan = ApplicationPlan(posting=p, match=strong_match())
        plan.resume = GeneratedResume(pdf_path=str(self.pdf))
        return plan

    def test_greenhouse_maps_fields_and_posts_resume(self):
        transport = FakeTransport()
        adapter = AtsAdapter(self.cfg, self.answers, transport=transport)
        plan = self._plan(
            posting(source="greenhouse", job_id="123", apply_url="https://boards.greenhouse.io/acme/jobs/123")
        )
        ok, reason = adapter.can_submit(plan)
        self.assertTrue(ok, reason)
        result = adapter.submit(plan)
        self.assertEqual(result.status, "submitted")
        url, fields, files = transport.calls[0]
        self.assertEqual(url, "https://boards.greenhouse.io/acme/jobs/123")
        self.assertEqual(fields["first_name"], "Abhigyan")
        self.assertEqual(fields["last_name"], "Sharma")
        self.assertEqual(fields["email"], "abhigyan@example.com")
        self.assertIn("resume", files)
        self.assertEqual(files["resume"][2], "application/pdf")

    def test_lever_uses_public_apply_endpoint(self):
        transport = FakeTransport()
        adapter = AtsAdapter(self.cfg, self.answers, transport=transport)
        plan = self._plan(
            posting(source="lever", job_id="abc", apply_url="https://jobs.lever.co/spotify/abc/apply")
        )
        result = adapter.submit(plan)
        self.assertEqual(result.status, "submitted")
        url, fields, _files = transport.calls[0]
        self.assertEqual(url, "https://jobs.lever.co/spotify/abc/apply")
        self.assertEqual(fields["name"], "Abhigyan Sharma")
        self.assertEqual(fields["urls[GitHub]"], "https://github.com/abhigyan")

    def test_missing_required_field_is_refused(self):
        transport = FakeTransport()
        adapter = AtsAdapter(self.cfg, AnswerBook(answers={}, profile=None), transport=transport)
        plan = self._plan(
            posting(source="greenhouse", job_id="9", apply_url="https://boards.greenhouse.io/acme/jobs/9")
        )
        ok, reason = adapter.can_submit(plan)
        self.assertFalse(ok)
        self.assertIn("email", reason)
        self.assertEqual(transport.calls, [])

    def test_non_2xx_is_failed(self):
        transport = FakeTransport(status=422, body="bad")
        adapter = AtsAdapter(self.cfg, self.answers, transport=transport)
        plan = self._plan(
            posting(source="lever", job_id="zzz", apply_url="https://jobs.lever.co/spotify/zzz/apply")
        )
        result = adapter.submit(plan)
        self.assertEqual(result.status, "failed")

    def test_default_adapter_routes_unsupported_board_to_review(self):
        cfg = test_config(Path(self.tmp.name))
        store = Store(":memory:")
        try:
            adapter = build_adapter(cfg, self.answers)
            self.assertEqual(adapter.name, "ats")
            applier = Applier(store, cfg, adapter, cfg.output.dir)
            plan = self._plan(posting(source="ashby", job_id="a-1"))
            outcome = applier.process(plan)
            self.assertEqual(outcome.action, "review")
            queued = [r["stable_id"] for r in store.list_review("pending")]
            self.assertIn(plan.posting.stable_id, queued)
        finally:
            store.close()


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
