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


if __name__ == "__main__":
    unittest.main()
