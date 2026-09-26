"""Tests for deadline extraction, urgency, expiry and staleness.

The parser never guesses: only a date stated next to an application cue counts,
a bare date or ambiguous numeric form yields nothing, and absence never changes
a posting's status. A *past* deadline closes the posting through the shared
open-state check; the deadline parser itself never filters.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from jobpilot.config import default_config
from jobpilot.deadline import (
    deadline_status,
    extract_deadline,
    format_deadline,
    is_stale,
    parse_iso_deadline,
    staleness_days,
)
from jobpilot.matching import Matcher
from jobpilot.pipeline import run_manual_pipeline
from jobpilot.store import Store
from jobpilot.window import classify_window
from tests.helpers import posting, test_config


class ExtractDeadlineTests(unittest.TestCase):
    def _extract(self, description, title="Machine Learning Intern"):
        return extract_deadline(posting(title=title, description=description))

    def test_apply_by_iso(self):
        self.assertEqual(self._extract("Apply by 2026-03-15."), "2026-03-15")

    def test_applications_close_month_name(self):
        self.assertEqual(self._extract("Applications close on March 15, 2026."), "2026-03-15")

    def test_application_deadline_day_first(self):
        self.assertEqual(self._extract("Application deadline: 15 March 2026"), "2026-03-15")

    def test_deadline_range_takes_the_end(self):
        self.assertEqual(
            self._extract("Applications accepted 2025-02-01 through 2025-03-15."),
            "2025-03-15",
        )

    def test_internship_window_after_the_deadline_is_not_the_deadline(self):
        self.assertEqual(
            self._extract("Apply before 2026-03-15. The internship runs 2026-06-01 to 2026-08-01."),
            "2026-03-15",
        )

    def test_cohort_date_after_the_deadline_is_not_the_deadline(self):
        self.assertEqual(
            self._extract("Apply by 2026-03-15 to be considered for the June 1, 2026 cohort."),
            "2026-03-15",
        )

    def test_generic_closure_does_not_outrank_an_explicit_cue(self):
        self.assertEqual(
            self._extract("The office closes on 2026-12-25 for the holidays. Apply by 2026-03-15."),
            "2026-03-15",
        )

    def test_weak_cue_does_not_reach_into_the_internship_window(self):
        self.assertEqual(
            self._extract(
                "Applications are open. The internship runs June 1, 2026 to August 1, 2026."
            ),
            "",
        )

    def test_weak_cue_does_not_treat_a_same_sentence_window_as_a_range(self):
        self.assertEqual(
            self._extract(
                "Applications are open for the internship running June 1, 2026 to August 1, 2026."
            ),
            "",
        )

    def test_accepted_until_does_not_reach_into_the_internship_window(self):
        self.assertEqual(
            self._extract(
                "Applications are accepted until positions are filled. "
                "The internship runs 2026-06-01 to 2026-08-01."
            ),
            "",
        )

    def test_ordinal_day(self):
        self.assertEqual(self._extract("Apply before 3rd April 2026."), "2026-04-03")

    def test_no_cue_means_no_deadline(self):
        # An internship window is not a deadline.
        self.assertEqual(self._extract("Internship runs January 2026 - June 2026."), "")

    def test_bare_date_without_a_cue_is_ignored(self):
        self.assertEqual(self._extract("Join us on 2026-03-15 in Bengaluru."), "")

    def test_ambiguous_numeric_date_is_never_guessed(self):
        self.assertEqual(self._extract("Apply by 15/03/2026."), "")

    def test_cue_without_a_date_yields_nothing(self):
        self.assertEqual(self._extract("Deadline: rolling admissions."), "")

    def test_newline_between_cue_and_date_is_not_a_sentence_boundary(self):
        self.assertEqual(self._extract("Deadline:\nMarch 15, 2026"), "2026-03-15")
        self.assertEqual(self._extract("Apply by\nMarch 15, 2026"), "2026-03-15")

    def test_abbreviated_month_is_not_a_sentence_boundary(self):
        self.assertEqual(self._extract("Apply by Mar. 15, 2026."), "2026-03-15")
        self.assertEqual(self._extract("Application deadline: Sept. 15, 2026."), "2026-09-15")

    def test_explicit_close_outranks_the_opening_date(self):
        self.assertEqual(
            self._extract("Applications open January 1, 2026 and close February 1, 2026."),
            "2026-02-01",
        )
        self.assertEqual(
            self._extract("Applications open 2026-01-01 and close 2026-02-01."),
            "2026-02-01",
        )

    def test_non_application_closure_is_not_a_deadline(self):
        self.assertEqual(
            self._extract("Our office closes on December 25, 2026 for the holidays. We are hiring interns."),
            "",
        )

    def test_single_opening_date_is_not_a_deadline(self):
        self.assertEqual(self._extract("Applications open 2026-01-01."), "")
        self.assertEqual(self._extract("Applications are accepted January 1, 2026."), "")

    def test_accepted_until_still_returns_its_close_date(self):
        self.assertEqual(
            self._extract("Applications are accepted until March 15, 2026."),
            "2026-03-15",
        )

    def test_non_application_open_until_is_not_a_deadline(self):
        self.assertEqual(
            self._extract("Our office is open until December 25, 2026 for the holidays."),
            "",
        )
        self.assertEqual(self._extract("The campus remains open through June 30, 2026."), "")

    def test_semicolon_joined_internship_window_is_not_the_deadline(self):
        self.assertEqual(
            self._extract(
                "Applications are accepted until positions are filled; "
                "the internship runs June 1, 2026 to August 1, 2026."
            ),
            "",
        )
        self.assertEqual(
            self._extract("The role is open until filled; internship runs 2026-06-01 to 2026-08-01."),
            "",
        )

    def test_joined_internship_window_is_not_the_deadline(self):
        # A cue that states no date must never reach a later clause's window.
        self.assertEqual(
            self._extract(
                "Applications are accepted until positions are filled, "
                "and the internship runs June 1, 2026 to August 1, 2026."
            ),
            "",
        )
        self.assertEqual(
            self._extract(
                "Applications are open until positions are filled, "
                "with the internship running June 1, 2026 to August 1, 2026."
            ),
            "",
        )
        self.assertEqual(
            self._extract(
                "Applications are accepted until positions are filled, internship starts 2026-06-01."
            ),
            "",
        )

    def test_cue_adjacent_range_is_not_extended_to_a_following_window(self):
        # The cue's own date is the deadline; a connector to a later date in the
        # posting is never followed on to a window end.
        self.assertNotEqual(
            self._extract("Applications are accepted until March 15, 2026 to August 1, 2026."),
            "2026-08-01",
        )

    def test_separator_between_cue_and_date_is_optional(self):
        self.assertEqual(self._extract("Apply: March 15, 2026"), "2026-03-15")
        self.assertEqual(self._extract("Apply - March 15, 2026"), "2026-03-15")
        self.assertEqual(self._extract("Applications close: March 15, 2026"), "2026-03-15")
        self.assertEqual(self._extract("Applications close March 15, 2026"), "2026-03-15")
        self.assertEqual(self._extract("Applications close:March 15, 2026"), "2026-03-15")

    def test_opening_date_alone_never_marks_a_posting_expired(self):
        p = posting(description="Applications open 2026-01-01.")
        deadline = extract_deadline(p)
        self.assertEqual(deadline, "")
        self.assertEqual(format_deadline(deadline, today=date(2026, 9, 24)), "")

    def test_extraction_does_not_make_the_window_verified(self):
        p = posting(
            description="Machine learning internship. Applications accepted 2025-01-05 through 2025-05-30."
        )
        self.assertEqual(extract_deadline(p), "2025-05-30")
        window = classify_window(p.searchable_text(), default_config().filter, prose=p.description)
        self.assertIsNone(window.overlaps)


class ParseIsoTests(unittest.TestCase):
    def test_valid_iso(self):
        self.assertEqual(parse_iso_deadline("2026-03-15"), date(2026, 3, 15))
        self.assertEqual(parse_iso_deadline("2026-03-15T00:00:00Z"), date(2026, 3, 15))

    def test_defensive_rejects_non_iso(self):
        for value in ("ASAP", "15.03.2026", "March 15", "", None, 20260315, "2026-13-40"):
            self.assertIsNone(parse_iso_deadline(value), value)


class DeadlineStatusTests(unittest.TestCase):
    TODAY = date(2026, 3, 10)

    def test_expired(self):
        self.assertEqual(deadline_status("2026-03-01", today=self.TODAY), "expired")

    def test_closing_soon(self):
        self.assertEqual(deadline_status("2026-03-15", today=self.TODAY), "closing_soon")
        self.assertEqual(deadline_status("2026-03-10", today=self.TODAY), "closing_soon")

    def test_open(self):
        self.assertEqual(deadline_status("2026-04-15", today=self.TODAY), "open")

    def test_absent_or_unparseable_is_blank(self):
        self.assertEqual(deadline_status("", today=self.TODAY), "")
        self.assertEqual(deadline_status("soon", today=self.TODAY), "")

    def test_format_label(self):
        self.assertEqual(format_deadline("2026-03-01", today=self.TODAY), "2026-03-01 (expired)")
        self.assertEqual(format_deadline("2026-03-15", today=self.TODAY), "2026-03-15 (closing soon)")
        self.assertEqual(format_deadline("nope", today=self.TODAY), "")


class StalenessTests(unittest.TestCase):
    TODAY = date(2026, 3, 10)

    def test_iso_and_timestamp(self):
        self.assertEqual(staleness_days("2026-02-08", today=self.TODAY), 30)
        self.assertEqual(staleness_days("2026-02-08T12:00:00Z", today=self.TODAY), 30)

    def test_unparseable_is_none(self):
        self.assertIsNone(staleness_days("", today=self.TODAY))
        self.assertIsNone(staleness_days("not a date", today=self.TODAY))

    def test_is_stale_threshold(self):
        self.assertFalse(is_stale("2026-02-20", today=self.TODAY, stale_days=30))
        self.assertTrue(is_stale("2026-01-01", today=self.TODAY, stale_days=30))


class PipelineDeadlinePersistenceTests(unittest.TestCase):
    def test_deadline_is_extracted_and_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = test_config(Path(tmp))
            p = posting(
                source="internshala",
                job_id="deadline-1",
                description="Machine learning internship, January 2026 - June 2026. Apply by 2026-03-15.",
            )
            # Stub the generation/compile path; this test is about persistence.
            from unittest import mock

            with mock.patch("jobpilot.pipeline._generate_and_fit") as fit:
                from jobpilot.models import GeneratedResume

                fit.return_value = (GeneratedResume(page_count=1, page_limit=1), True)
                with mock.patch("jobpilot.pipeline._run_parseability"):
                    run_manual_pipeline(cfg, p)

            store = Store(cfg.resolve(cfg.output.database))
            try:
                row = store.get_posting(p.stable_id)
                self.assertEqual(row["deadline"], "2026-03-15")
                listed = store.list_postings()
                self.assertEqual(listed[0]["deadline"], "2026-03-15")
            finally:
                store.close()

    def test_match_does_not_change_with_a_deadline(self):
        cfg = test_config()
        profile = __import__("tests.helpers", fromlist=["mini_profile"]).mini_profile()
        plain = posting(description="Machine learning internship. Python, RAG.")
        dated = posting(description="Machine learning internship. Python, RAG. Apply by 2026-03-15.")
        a = Matcher(profile, cfg).match(plain)
        b = Matcher(profile, cfg).match(dated)
        self.assertEqual(a.score, b.score)


if __name__ == "__main__":
    unittest.main()
