"""Tests for deterministic stipend extraction and the monthly floor.

Every form the captain's corpus actually contains must classify without
inventing an amount: the confirmed forms clear or fail the floor, the explicit
negatives are unpaid, and a stipend mentioned without a figure is ``unstated``
(shown separately) rather than dropped or guessed.
"""

from __future__ import annotations

import unittest

from jobpilot.stipend import (
    CONFIRMED_BELOW_FLOOR,
    CONFIRMED_GE_FLOOR,
    UNPAID,
    UNSTATED,
    classify_stipend,
)


class ParseFormsTests(unittest.TestCase):
    def test_floor_at_least_30000(self):
        self.assertEqual(classify_stipend("Stipend: ₹30,000").state, CONFIRMED_GE_FLOOR)
        self.assertEqual(classify_stipend("Stipend: ₹40,000/month").state, CONFIRMED_GE_FLOOR)
        self.assertEqual(classify_stipend("Stipend: ₹29,999/month").state, CONFIRMED_BELOW_FLOOR)

    def test_corpus_range_and_of_forms(self):
        info = classify_stipend("Stipend: INR 15,000-18,000/ month")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(info.amount, 15000)
        self.assertEqual(info.amount_high, 18000)

        self.assertEqual(classify_stipend("Stipend of ₹10,000").state, CONFIRMED_BELOW_FLOOR)

        info = classify_stipend("Stipend range- Rs 5000 - Rs 10000")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual((info.amount, info.amount_high), (5000, 10000))

    def test_per_month_and_shorthand_forms(self):
        self.assertEqual(classify_stipend("Stipend: 3000 Per month").amount, 3000)
        self.assertEqual(classify_stipend("INR 5K stipend per month").amount, 5000)
        self.assertEqual(classify_stipend("Stipend: 1K").amount, 1000)
        self.assertEqual(classify_stipend("Stipend: 1.5K per month").amount, 1500)
        info = classify_stipend("Stipend: 12-15k per month")
        self.assertEqual((info.amount, info.amount_high), (12000, 15000))

    def test_bare_currency_and_period_variants(self):
        self.assertEqual(classify_stipend("₹30,000").state, CONFIRMED_GE_FLOOR)
        self.assertEqual(classify_stipend("bare INR 40000").amount, 40000)
        for text in (
            "₹35,000/month",
            "₹35,000/mo",
            "₹35,000 pm",
            "₹35,000 per month",
            "₹35,000 monthly",
        ):
            self.assertEqual(classify_stipend(text).state, CONFIRMED_GE_FLOOR, text)

    def test_range_is_judged_by_its_lower_bound(self):
        info = classify_stipend("Stipend: ₹25,000-35,000/month")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(info.amount, 25000)
        self.assertEqual(info.amount_high, 35000)

    def test_explicit_annual_figure_is_converted_to_monthly(self):
        info = classify_stipend("Stipend: ₹3,00,000 per annum")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(info.amount, 25000)  # 3,00,000 / 12

    def test_floor_is_configurable(self):
        self.assertEqual(classify_stipend("₹25,000/month", floor=20000).state, CONFIRMED_GE_FLOOR)
        self.assertEqual(classify_stipend("₹25,000/month", floor=30000).state, CONFIRMED_BELOW_FLOOR)


class NegativeFormsTests(unittest.TestCase):
    def test_explicit_unpaid_and_no_stipend(self):
        for text in (
            "Unpaid",
            "Stipend: unpaid",
            "No Stipend! The completion certificate will be provided.",
            "There will be no stipend provided.",
            "No fixed stipend; earnings are variable.",
        ):
            self.assertEqual(classify_stipend(text).state, UNPAID, text)

    def test_performance_and_commission_only(self):
        for text in (
            "Performance-Based Stipend",
            "Stipend: Performance-based",
            "The stipend is based on performance.",
            "commission only",
            "Fixed+Performance based stipend",
        ):
            self.assertEqual(classify_stipend(text).state, UNPAID, text)

    def test_unpaid_beats_a_stray_figure(self):
        self.assertEqual(
            classify_stipend("Unpaid internship; certificate worth ₹5,000").state, UNPAID
        )

    def test_confirmed_figure_below_floor_is_below_not_unpaid(self):
        info = classify_stipend("₹18,000/month fixed stipend + incentives based on performance")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)

    def test_a_stipend_without_a_figure_is_unstated_not_invented(self):
        # The captain chose: confirmed amounts are shown, unknown ones are flagged
        # separately. "stipend will be provided" states no figure, so it must be
        # visible as unstated - never treated as a confirmed amount or dropped.
        for text in (
            "stipend will be provided",
            "Stipend:",
            "Monthly stipend is negotiable.",
            "The stipend amount will be determined later.",
        ):
            self.assertEqual(classify_stipend(text).state, UNSTATED, text)

    def test_no_stipend_information_at_all(self):
        info = classify_stipend("Machine learning internship. Python, RAG, LLMs.")
        self.assertEqual(info.state, UNSTATED)
        self.assertEqual(info.display_label(), "stipend not stated")


class DisplayTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(
            classify_stipend("₹40,000/month").display_label(), "₹40,000/mo confirmed"
        )
        self.assertIn("below floor", classify_stipend("₹10,000/month").display_label())
        self.assertEqual(
            classify_stipend("Machine learning internship.").display_label(), "stipend not stated"
        )
        self.assertEqual(classify_stipend("Unpaid").display_label(), "unpaid / no fixed stipend")

    def test_dropped_flag(self):
        self.assertTrue(classify_stipend("Unpaid").dropped)
        self.assertTrue(classify_stipend("₹10,000/month").dropped)
        self.assertFalse(classify_stipend("₹30,000/month").dropped)
        self.assertFalse(classify_stipend("no figure here").dropped)


if __name__ == "__main__":
    unittest.main()
