"""Tests for the shared application open-state decision.

Unstop marked rows ``LIVE`` while their application was closed; the decision
must reject on a falsy ``regn_open``, a past ``end_date``, closed posting text,
or a stated past deadline (for every adapter), while treating a missing end date
or missing registration metadata as unverified - never closed.
"""

from __future__ import annotations

import unittest
from datetime import date

from jobpilot.filtering import filter_posting, open_state_check
from jobpilot.openstate import OpenState, assess_open_state
from tests.helpers import posting, test_config

TODAY = date(2026, 9, 26)
PAST = "2026-01-05"
FUTURE = "2030-06-30"


def _unstop(**raw):
    p = posting(source="unstop", title="Machine Learning Intern")
    p.raw = raw
    return p


class AssessOpenStateTests(unittest.TestCase):
    def test_regn_open_falsy_is_closed(self):
        state = assess_open_state(_unstop(regn_open=0, end_date=FUTURE), today=TODAY)
        self.assertTrue(state.closed)
        self.assertIn("regn_open", state.reason)

    def test_regn_open_string_zero_is_closed(self):
        state = assess_open_state(_unstop(regn_open="0", end_date=FUTURE), today=TODAY)
        self.assertTrue(state.closed)

    def test_past_end_date_is_closed_even_when_regn_open_is_one(self):
        state = assess_open_state(_unstop(regn_open=1, end_date=PAST), today=TODAY)
        self.assertTrue(state.closed)
        self.assertIn("registration ended", state.reason)

    def test_future_end_date_with_registration_open_is_open(self):
        state = assess_open_state(_unstop(regn_open=1, end_date=FUTURE), today=TODAY)
        self.assertIs(state.open, True)

    def test_unknown_end_date_is_open_but_unverified(self):
        state = assess_open_state(_unstop(regn_open=1), today=TODAY)
        self.assertIs(state.open, True)

    def test_past_end_date_without_regn_open_is_still_closed(self):
        # The spec rejects on a past end_date directly, not only when regn_open
        # is present.
        state = assess_open_state(_unstop(end_date=PAST), today=TODAY)
        self.assertTrue(state.closed)

    def test_row_with_no_registration_fields_at_all_is_unverified(self):
        p = posting(source="unstop", title="Machine Learning Intern")
        p.raw = {}
        state = assess_open_state(p, today=TODAY)
        self.assertIsNone(state.open)
        self.assertFalse(state.closed)

    def test_closed_text_is_closed(self):
        for text in (
            "Machine learning internship. Applications closed.",
            "Application closed for this role.",
            "We are no longer accepting applications.",
        ):
            state = assess_open_state(posting(description=text), today=TODAY)
            self.assertTrue(state.closed, text)

    def test_past_stated_deadline_is_closed_for_any_source(self):
        p = posting(
            source="greenhouse",
            description="Machine learning internship. Python, RAG. Apply by 2026-01-05.",
        )
        state = assess_open_state(p, today=TODAY)
        self.assertTrue(state.closed)
        self.assertIn("2026-01-05", state.reason)

    def test_no_signal_is_unverified(self):
        state = assess_open_state(posting(description="Machine learning internship."), today=TODAY)
        self.assertIsNone(state.open)

    def test_headless_apply_range_still_open_is_not_closed(self):
        # The opening date of the application range is in the past but the close
        # is in the future, so the posting must stay open, not be rejected.
        p = posting(
            source="greenhouse",
            description=(
                "Machine Learning internship. You may apply 2026-01-01 to 2026-12-31. "
                "Python, RAG."
            ),
        )
        state = assess_open_state(p, today=TODAY)
        self.assertFalse(state.closed)


class FilterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()

    def test_filter_rejects_a_past_deadline_for_a_non_unstop_adapter(self):
        p = posting(
            source="greenhouse",
            job_id="past-deadline",
            description="Machine learning internship. Python, RAG. Apply by 2020-01-05.",
        )
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("application_open" in r for r in result.reject_reasons))

    def test_filter_rejects_closed_text(self):
        p = posting(job_id="closed-text", description="Machine learning internship. Applications closed.")
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("application_open" in r for r in result.reject_reasons))

    def test_filter_rejects_unstop_past_end_date_when_metadata_present(self):
        p = _unstop(regn_open=1, end_date="2020-01-05")
        result = filter_posting(p, self.cfg.filter)
        self.assertFalse(result.eligible)
        self.assertTrue(any("application_open" in r for r in result.reject_reasons))

    def test_filter_keeps_unstop_open_row_with_future_end_date(self):
        p = _unstop(regn_open=1, end_date="2030-06-30")
        result = filter_posting(p, self.cfg.filter)
        self.assertTrue(result.eligible, result.reject_text())

    def test_no_registration_metadata_is_unverified_not_rejected(self):
        # A synthetic row with no registration fields must not be assumed closed.
        p = posting(source="unstop", title="Machine Learning Intern")
        p.raw = {}
        result = open_state_check(p, self.cfg.filter)
        self.assertTrue(result.passed)

    def test_open_state_object_only_closed_on_false(self):
        self.assertTrue(OpenState(False).closed)
        self.assertFalse(OpenState(None).closed)
        self.assertFalse(OpenState(True).closed)


if __name__ == "__main__":
    unittest.main()
