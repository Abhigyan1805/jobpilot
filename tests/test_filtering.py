import unittest

from jobpilot.filtering import filter_posting
from jobpilot.window import classify_window
from tests.helpers import posting, test_config


class FilteringTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()

    def test_internship_in_india_passes(self):
        p = posting(
            title="Machine Learning Intern",
            location="Bengaluru, India",
            description="A machine learning internship running January 2026 - June 2026.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertTrue(result.eligible, result.reject_reasons)
        self.assertTrue(result.window_label)

    def test_remote_intern_passes(self):
        p = posting(title="Data Science Intern", location="Remote - Worldwide", is_remote=True)
        self.assertTrue(filter_posting(p, self.cfg.filter).eligible)

    def test_fulltime_role_rejected(self):
        p = posting(
            title="Senior Software Engineer",
            employment_type="FullTime",
            description="A full-time role for an experienced engineer.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("internship" in r or "seniority" in r for r in result.reject_reasons))

    def test_intern_substring_is_not_an_internship(self):
        p = posting(
            title="Internal Tools Engineer",
            employment_type="FullTime",
            description="Build internal platforms and tooling.",
        )
        self.assertFalse(filter_posting(p, self.cfg.filter).eligible)

    def test_us_only_intern_rejected(self):
        p = posting(
            title="Research Intern",
            location="San Francisco, United States",
            description="Summer 2026 internship. Must be authorized to work in the US; onsite.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("india" in r for r in result.reject_reasons))

    def test_out_of_window_rejected(self):
        p = posting(
            title="Software Intern",
            location="Remote - Worldwide",
            is_remote=True,
            description="Fall 2026 internship running September to December 2026.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("window" in r for r in result.reject_reasons))

    def test_window_classifier(self):
        cfg = self.cfg.filter
        self.assertTrue(classify_window("January 2026 - June 2026", cfg).overlaps)
        self.assertFalse(classify_window("September to December 2026", cfg).overlaps)
        self.assertTrue(classify_window("Summer 2026 internship", cfg).overlaps)
        self.assertIsNone(classify_window("great internship", cfg).overlaps)


if __name__ == "__main__":
    unittest.main()
