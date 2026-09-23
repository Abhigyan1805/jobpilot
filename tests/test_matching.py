import unittest

from jobpilot.matching import Matcher
from tests.helpers import mini_profile, posting, test_config


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()
        self.profile = mini_profile()
        self.matcher = Matcher(self.profile, self.cfg)

    def test_coverage_splits_matched_and_missing(self):
        p = posting(
            description=(
                "Machine learning internship. Python, RAG, LLMs and evaluation. "
                "Kubernetes and TensorFlow experience required."
            )
        )
        result = self.matcher.match(p)
        self.assertIn("RAG", result.coverage.matched)
        self.assertIn("Python", result.coverage.matched)
        self.assertIn("Kubernetes", result.missing_keywords)
        self.assertIn("TensorFlow", result.missing_keywords)
        # Missing terms must never be injected into the resume.
        self.assertNotIn("Kubernetes", result.coverage.matched)

    def test_unsupported_terms_reported_as_gaps_not_added(self):
        p = posting(description="Internship requiring Terraform and Kubernetes only.")
        result = self.matcher.match(p)
        self.assertTrue(result.missing_keywords)
        for term in result.missing_keywords:
            self.assertNotIn(term, self.profile.raw_text)

    def test_score_is_bounded_and_documented(self):
        p = posting(description="Machine learning internship with Python, RAG, LLMs, evaluation.")
        result = self.matcher.match(p)
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)
        rubric = result.rubric
        self.assertIn("weights", rubric)
        self.assertIn("formula", rubric)
        self.assertEqual(set(rubric["components"]), set(self.cfg.match.weights))
        self.assertIn("does not predict hiring outcomes", rubric["description"])

    def test_strong_relevant_role_outranks_irrelevant(self):
        good = posting(
            title="Machine Learning Intern",
            description="Machine learning internship with Python, RAG, LLMs, evaluation and statistics.",
        )
        weak = posting(
            title="Marketing Intern",
            description="Marketing internship focused on campaigns and social media.",
        )
        self.assertGreater(self.matcher.match(good).score, self.matcher.match(weak).score)

    def test_zero_role_relevance_is_capped_out_of_the_strong_band(self):
        # An unrelated India internship with an ideal window and full keyword
        # coverage clears the score threshold; role relevance must still keep it
        # out of `strong`, which is the auto-apply band.
        description = (
            "Machine learning internship, January 2026 - June 2026. Python, RAG, LLMs, "
            "evaluation, forecasting, SQL, Docker."
        )
        unrelated = posting(title="Talent Acquisition Intern", description=description)
        relevant = posting(title="Machine Learning Intern", description=description)

        capped = self.matcher.match(unrelated)
        strong = self.matcher.match(relevant)

        self.assertGreaterEqual(capped.score, self.cfg.match.strong_threshold)
        self.assertEqual(capped.band, "shortlist")
        self.assertLess(capped.rubric["components"]["role_relevance"]["score"], 0.5)
        self.assertTrue(any("strong band withheld" in reason for reason in capped.reasons))
        # A genuinely relevant AI/ML internship still reaches strong.
        self.assertEqual(strong.band, "strong")

    def test_target_domains_are_config_driven_not_hardcoded(self):
        p = posting(
            title="UX Design Intern",
            description="Internship, January 2026 - June 2026. Design wireframes and prototyping.",
        )
        self.assertNotEqual(self.matcher.match(p).band, "strong")

        design_cfg = test_config(
            match={
                "target_terms": {"design": ["ux design", "wireframes", "prototyping"]},
                "strong_min_role_relevance": 0.5,
            }
        )
        design_match = Matcher(self.profile, design_cfg).match(p)
        self.assertEqual(design_match.band, "strong")

    def test_company_boilerplate_does_not_inflate_role_relevance(self):
        # The exact defect: a UX design internship whose company blurb mentions
        # machine learning must not look AI-relevant or outrank a genuine SWE
        # internship. The blurb text sits above the role section.
        ux = posting(
            title="UX Design Intern",
            description=(
                "Acme builds a machine learning and generative AI platform for data "
                "science teams.\n"
                "What you'll do\n"
                "- Design wireframes, prototypes and a design system\n"
                "- Collaborate with engineers on the TV canvas\n"
            ),
        )
        swe = posting(
            title="Software Engineer Intern",
            description=(
                "Acme is a global technology company.\n"
                "Your Role\n"
                "- Build backend services with Python, SQL and Docker\n"
                "- Design REST APIs and deployment pipelines\n"
            ),
        )
        ux_result = self.matcher.match(ux)
        swe_result = self.matcher.match(swe)

        self.assertEqual(ux_result.band, "shortlist")
        self.assertLess(ux_result.rubric["components"]["role_relevance"]["score"], 0.5)
        self.assertGreater(swe_result.score, ux_result.score)


if __name__ == "__main__":
    unittest.main()
