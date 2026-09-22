import tempfile
import unittest

from jobpilot.facts import bold_measurements, extract_numbers
from jobpilot.matching import Matcher
from jobpilot.resume.generator import ContentInvariantError, RenderedResume, ResumeGenerator
from tests.helpers import mini_profile, posting, test_config


class NoInventionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()
        self.profile = mini_profile()
        self.gen = ResumeGenerator(self.profile, self.cfg)
        self.posting = posting(
            description="Machine learning internship. Python, RAG, LLMs, evaluation, statistics, forecasting."
        )
        self.match = Matcher(self.profile, self.cfg).match(self.posting)

    def test_generated_content_has_no_invented_facts(self):
        rendered = self.gen.render(self.posting, self.match)
        self.assertEqual([], self.gen.validate_content(rendered))
        for item in rendered.provenance:
            self.assertTrue(self.gen.validator.is_clean(item["raw"]), item["raw"])

    def test_every_number_in_resume_is_in_profile(self):
        rendered = self.gen.render(self.posting, self.match)
        profile_numbers = extract_numbers(self.profile.raw_text)
        for item in rendered.provenance:
            for number in extract_numbers(item["raw"]):
                self.assertIn(number, profile_numbers, f"{number} not in profile: {item['raw']}")

    def test_injected_fact_is_rejected(self):
        violations = self.gen.validator.validate("Increased revenue by 300% using quantum computing")
        pairs = {(v.kind, v.token) for v in violations}
        self.assertTrue(any(kind == "number" and token.startswith("300") for kind, token in pairs), pairs)
        self.assertTrue(any(kind == "unknown-word" for kind, _ in pairs))

    def test_generate_raises_on_invented_content(self):
        bad = RenderedResume(
            body="x",
            sections=[],
            content_text="",
            provenance=[{"raw": "Achieved 999% growth", "source": self.profile.raw_text, "ref": "x"}],
        )
        original = self.gen.render
        self.gen.render = lambda *a, **k: bad
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ContentInvariantError):
                    self.gen.generate(self.posting, self.match, tmp)
        finally:
            self.gen.render = original

    def test_bold_emphasis_changes_only_formatting(self):
        source = "improving accuracy by 12% on 500 records"
        out = bold_measurements(source)
        self.assertEqual(out.replace("\\textbf{", "").replace("}", ""), source)


if __name__ == "__main__":
    unittest.main()
