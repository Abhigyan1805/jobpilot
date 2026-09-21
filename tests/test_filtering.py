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
        p = posting(
            title="Data Science Intern",
            location="Remote - Worldwide",
            is_remote=True,
            description="Data science internship running January 2026 - June 2026.",
        )
        self.assertTrue(filter_posting(p, self.cfg.filter).eligible)

    def test_unknown_window_is_eligible_for_review_not_rejected(self):
        p = posting(title="Data Science Intern", location="Remote - Worldwide", is_remote=True)
        result = filter_posting(p, self.cfg.filter)
        self.assertTrue(result.eligible, result.reject_reasons)
        self.assertEqual(result.window_label, "unknown")
        self.assertFalse(any("window" in r for r in result.reject_reasons))

    def test_unknown_window_allowed_when_configured(self):
        cfg = test_config(filt={"allow_unknown_window": True})
        p = posting(title="Data Science Intern", location="Remote - Worldwide", is_remote=True)
        self.assertTrue(filter_posting(p, cfg.filter).eligible)

    def test_fulltime_graduate_program_rejected(self):
        p = posting(
            title="Graduate Program - Software Engineer",
            employment_type="FullTime",
            location="Bengaluru, India",
            description="A full-time graduate program for software engineers, January to June 2026.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("fulltime" in r or "internship" in r for r in result.reject_reasons))

    def test_global_word_in_description_does_not_admit_onsite_us(self):
        p = posting(
            title="Software Engineering Intern",
            location="San Francisco, United States",
            description="Join our global team building products. January - June 2026 internship.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("india" in r for r in result.reject_reasons))

    def test_technology_name_does_not_corrupt_window(self):
        p = posting(
            title="Software Engineering Intern",
            location="Remote - Worldwide",
            is_remote=True,
            description="Tech stack: Java, Spring Boot. Our fall internship is a 6-month placement.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("window" in r for r in result.reject_reasons))

    def test_season_near_internship_still_detected(self):
        cfg = self.cfg.filter
        self.assertEqual(classify_window("Our fall internship runs late in the year.", cfg).overlaps, False)
        self.assertTrue(classify_window("A summer internship for 2026.", cfg).overlaps)
        self.assertIsNone(classify_window("Experience with Spring Boot required.", cfg).overlaps)
        self.assertEqual(
            classify_window("An internship using Spring Boot and running in the fall term.", cfg).overlaps,
            False,
        )

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
