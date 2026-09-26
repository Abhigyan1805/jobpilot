"""Tests for deterministic stipend extraction and the monthly floor.

Every form the captain's corpus actually contains must classify without
inventing an amount: the confirmed forms clear or fail the floor, the explicit
negatives are unpaid, and a stipend mentioned without a figure is ``unstated``
(shown separately) rather than dropped or guessed.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobpilot.stipend import (
    CONFIRMED_BELOW_FLOOR,
    CONFIRMED_GE_FLOOR,
    UNPAID,
    UNSTATED,
    classify_stipend,
)
from jobpilot.store import Store
from tests.helpers import posting


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

    def test_annual_adjective_is_read_as_a_yearly_figure(self):
        # "annual"/"yearly" as a preposed or postposed adjective is an annual
        # figure (₹3,00,000 / 12 = ₹25,000), not a monthly one.
        for text in (
            "Annual stipend: ₹3,00,000",
            "Stipend (annual): ₹3,00,000",
            "Stipend: ₹3,00,000 annual",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR, text)
            self.assertEqual(info.amount, 25000, text)
        # A preposed monthly form stays monthly.
        monthly = classify_stipend("Monthly stipend ₹30,000")
        self.assertEqual(monthly.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(monthly.amount, 30000)

    def test_a_period_inside_the_match_is_never_overridden_by_a_trailing_adjective(self):
        # An embedded "/month" must win over a following "annual <noun>", or a
        # qualifying posting is silently read as an annual package and dropped.
        for text in (
            "Stipend: ₹30,000/month annual contract",
            "Stipend: ₹30,000/month annual package",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertEqual(info.amount, 30000, text)
        # An explicit per-annum figure stays annual even with a trailing adjective.
        per_annum = classify_stipend("Stipend: ₹3,00,000 per annum annual")
        self.assertEqual(per_annum.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(per_annum.amount, 25000)

    def test_k_suffixed_range_is_detected_on_either_end(self):
        both = classify_stipend("Stipend: 30k - 40k /month")
        self.assertEqual(both.state, CONFIRMED_GE_FLOOR)
        self.assertEqual((both.amount, both.amount_high), (30000, 40000))
        self.assertEqual(both.display_label(), "₹30,000-40,000/mo confirmed")

        below = classify_stipend("Stipend: 10k-15k /month")
        self.assertEqual(below.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual((below.amount, below.amount_high), (10000, 15000))
        self.assertEqual(below.display_label(), "₹10,000-15,000/mo below floor")

    def test_mixed_full_number_and_k_range_does_not_scale_the_full_end(self):
        # Only the shorthand end carries the K, so a written-out lower bound
        # keeps its own value: the floor is judged against 25,000, not 30,000.
        info = classify_stipend("Stipend: 25,000-30k per month")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual((info.amount, info.amount_high), (25000, 30000))
        self.assertEqual(info.display_label(), "₹25,000-30,000/mo below floor")

        low = classify_stipend("Stipend: 8,000-10k per month")
        self.assertEqual((low.amount, low.amount_high), (8000, 10000))
        self.assertEqual(low.display_label(), "₹8,000-10,000/mo below floor")

    def test_floor_is_configurable(self):
        self.assertEqual(classify_stipend("₹25,000/month", floor=20000).state, CONFIRMED_GE_FLOOR)
        self.assertEqual(classify_stipend("₹25,000/month", floor=30000).state, CONFIRMED_BELOW_FLOOR)

    def test_currency_prefixed_shorthand_range_reads_the_whole_range(self):
        # The lower bound must not be read as a bare "40" amount: the whole
        # range is thousands, so it clears a ₹30,000 floor.
        info = classify_stipend("₹40-50k per month")
        self.assertEqual(info.state, CONFIRMED_GE_FLOOR)
        self.assertEqual((info.amount, info.amount_high), (40000, 50000))

    def test_non_monthly_period_is_not_read_as_monthly(self):
        # An hourly/weekly/daily rate must never clear (or fail) the monthly floor.
        for text in (
            "₹45,000 per hour",
            "Stipend: ₹45,000 per hour",
            "₹30,000 hourly",
            "₹30,000 weekly",
            "₹30,000 daily",
            "₹30,000 an hour",
            "Stipend: ₹30,000 per-hour",
            "Stipend: ₹30,000/hr",
            "₹500 hourly",
            "₹10,000 an hour",
        ):
            info = classify_stipend(text)
            self.assertNotEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertEqual(info.state, UNSTATED, text)
            self.assertFalse(info.dropped, text)
        weekly = classify_stipend("Stipend: ₹10,000/week")
        self.assertFalse(weekly.dropped)
        self.assertNotEqual(weekly.state, CONFIRMED_GE_FLOOR)

    def test_bare_year_with_trailing_comma_is_not_a_stipend(self):
        for text in (
            "Founded in 2015, our interns get a stipend.",
            "Established in 2020, the stipend is provided after training.",
        ):
            self.assertEqual(classify_stipend(text).state, UNSTATED, text)
            self.assertFalse(classify_stipend(text).dropped, text)

    def test_annual_figures_are_not_mangled(self):
        per_annum = classify_stipend("₹6,00,000 per annum")
        self.assertEqual(per_annum.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(per_annum.amount, 50000)
        self.assertNotIn("-", per_annum.display_label())

        lpa = classify_stipend("Stipend: 6 LPA")
        self.assertEqual(lpa.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(lpa.amount, 50000)

    def test_bare_lakh_abbreviation_is_scaled_annually(self):
        # "L"/"lac"/"Lakhs" is a lakh unit, not a stray leading digit: a figure
        # stated per annum (or with no period) is annual, so ₹4.8L is ₹40,000/mo.
        for text in (
            "Stipend: ₹4.8L per annum",
            "Stipend: 4.8L per year",
            "Stipend: ₹4.8 lac per annum",
            "Stipend: ₹4.8 Lakhs",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertEqual(info.amount, 40000, text)

    def test_lakh_figure_with_a_stated_month_stays_monthly(self):
        info = classify_stipend("Stipend: ₹4.8 Lakhs per month")
        self.assertEqual(info.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(info.amount, 480000)

    def test_explicit_two_thousand_amount_is_not_dropped_as_a_year(self):
        for text in ("₹2000/month", "Stipend: 2000 per month"):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR, text)
            self.assertEqual(info.amount, 2000, text)
        # A *bare* four-digit year is still not a stipend amount.
        self.assertEqual(classify_stipend("Stipend: 2026").state, UNSTATED)

    def test_pa_annual_and_lump_sum_totals_are_read_as_monthly(self):
        pa = classify_stipend("Stipend: ₹3,00,000 p.a.")
        self.assertEqual(pa.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(pa.amount, 25000)

        lump = classify_stipend("Stipend: ₹60,000 for 3 months")
        self.assertEqual(lump.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(lump.amount, 20000)

        clearing = classify_stipend("Stipend: ₹90,000 for 3 months")
        self.assertEqual(clearing.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(clearing.amount, 30000)


class GoverningFigureTests(unittest.TestCase):
    """The floor is judged against the governing stipend figure, not min() of
    every number: headcount, a benefit's worth, a one-time bonus and an
    allowance are not the base and must not drag a qualifying figure down."""

    def test_base_monthly_plus_smaller_one_time_bonus_qualifies(self):
        info = classify_stipend("Stipend: ₹30,000/month + a one-time ₹5,000 bonus")
        self.assertEqual(info.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(info.amount, 30000)
        self.assertEqual(info.amount_high, 30000)

    def test_base_monthly_plus_smaller_recurring_allowance_qualifies(self):
        info = classify_stipend("Stipend: ₹35,000/month; travel allowance 2,000/month")
        self.assertEqual(info.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(info.amount, 35000)
        self.assertEqual(info.amount_high, 35000)

    def test_headcount_and_benefit_worth_do_not_drag_the_base(self):
        headcount = classify_stipend("Stipend: ₹40,000/month. We have 40 employees.")
        self.assertEqual(headcount.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(headcount.amount, 40000)

        benefit = classify_stipend(
            "Stipend: ₹35,000/month. Training worth ₹10,000 provided."
        )
        self.assertEqual(benefit.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(benefit.amount, 35000)

    def test_fixed_figure_with_incentives_stays_confirmed(self):
        for text in (
            "Stipend: ₹30,000/month + incentives",
            "₹30,000 monthly + incentives",
            "₹30,000/month fixed + incentives",
            "₹30,000/month (fixed) + up to ₹5,000 bonus",
            "Stipend: ₹30,000/month with incentives",
            "Stipend: ₹30,000/month incentives included",
            "Stipend: 40,000 per month plus incentives",
            "Stipend: ₹30,000/month plus a joining bonus of ₹5,000.",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertTrue(info.amount and info.amount >= 30000, text)

    def test_stray_numbers_in_neighbouring_clauses_are_not_stipends(self):
        for text, expected in (
            ("Stipend: ₹30,000/month. 3+ years of experience preferred.", 30000),
            ("Stipend: ₹35,000/month. 2 rounds of interviews.", 35000),
            ("Stipend: ₹35,000/month. Office in Bengaluru 560001.", 35000),
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertEqual(info.amount, expected, text)
            self.assertEqual(info.amount_high, expected, text)

    def test_unrelated_figures_are_not_rendered_as_a_range(self):
        for text, label in (
            ("Stipend: ₹35,000/month. CTC: ₹6,00,000 per annum.", "₹35,000/mo confirmed"),
            (
                "Stipend: ₹35,000/month. ₹40,000/month for returning interns.",
                "₹35,000/mo confirmed",
            ),
        ):
            info = classify_stipend(text)
            self.assertEqual(info.display_label(), label, text)
            self.assertNotIn("-", info.display_label(), text)

    def test_fixed_base_outranks_a_conditional_stipend_figure(self):
        # The fixed monthly base is the figure the floor applies to; a nearby
        # performance-qualified "up to" figure must not suppress it.
        for text, amount in (
            (
                "Stipend: up to ₹50,000/month based on performance. Fixed ₹35,000/month.",
                35000,
            ),
            (
                "Stipend: up to ₹50,000/month based on performance. ₹35,000/month fixed.",
                35000,
            ),
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertEqual(info.amount, amount, text)

    def test_genuine_sub_floor_monthly_is_dropped(self):
        info = classify_stipend("Stipend: ₹10,000/month")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertTrue(info.dropped)

    def test_stipend_cue_outranks_an_earlier_package_figure(self):
        # An earlier CTC/salary figure over the floor must not override the
        # sub-floor monthly stipend that actually governs.
        for text in (
            "CTC ₹6,00,000/annum. Stipend ₹15,000/month.",
            "Annual salary: 6,00,000. Stipend: 15,000 per month",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR, text)
            self.assertEqual(info.amount, 15000, text)
            self.assertTrue(info.dropped, text)

    def test_range_high_comes_from_the_stated_stipend_range_not_a_package_figure(self):
        info = classify_stipend("Stipend: ₹30,000-40,000/month. CTC: ₹6,00,000 per annum.")
        self.assertEqual(info.state, CONFIRMED_GE_FLOOR)
        self.assertEqual((info.amount, info.amount_high), (30000, 40000))
        self.assertEqual(info.display_label(), "₹30,000-40,000/mo confirmed")

    def test_range_lower_bound_semantics_are_kept(self):
        below = classify_stipend("Stipend: ₹25,000-35,000/month")
        self.assertEqual(below.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(below.amount, 25000)

        qualifies = classify_stipend("Stipend: ₹30,000-40,000/month")
        self.assertEqual(qualifies.state, CONFIRMED_GE_FLOOR)
        self.assertEqual(qualifies.amount, 30000)

    def test_range_period_applies_to_both_ends(self):
        # The period is stated once, at the range's far end: it must govern the
        # lower bound too, not just the upper end that carries it.
        annual = classify_stipend("Stipend: ₹3,00,000-4,00,000 per annum")
        self.assertEqual(annual.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual((annual.amount, annual.amount_high), (25000, 33333))

        for text in (
            "Stipend: ₹30,000-40,000 per hour",
            "Stipend: ₹30,000-40,000 weekly",
            "Stipend: ₹2,000-3,000 per day",
            "Stipend: 1,500-2,000/day",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, UNSTATED, text)
            self.assertFalse(info.dropped, text)

    def test_benefit_word_sharing_a_stipend_clause_does_not_downgrade_it(self):
        for text, state, amount in (
            ("Stipend: ₹30,000/month (food and accommodation not included)", CONFIRMED_GE_FLOOR, 30000),
            ("Stipend: ₹30,000 per month for travel", CONFIRMED_GE_FLOOR, 30000),
            ("Stipend: 35,000 (Food and Accommodation provided)", CONFIRMED_GE_FLOOR, 35000),
            ("Stipend: ₹10,000 per month (travel allowance extra)", CONFIRMED_BELOW_FLOOR, 10000),
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, state, text)
            self.assertEqual(info.amount, amount, text)

    def test_cue_bearing_allowance_does_not_preempt_the_stipend_base(self):
        # A small labelled extras amount ("travel/internet stipend") shares the
        # strong stipend cue, so it must be read as an allowance, not the base,
        # and never drag the real ₹30,000 stipend below the floor.
        for text in (
            "Travel stipend ₹2,000/month. Stipend: ₹30,000/month.",
            "Internet stipend 1,000/month. Stipend: 30,000/month.",
            "Internet stipend: ₹1,000/month. Stipend: ₹30,000/month.",
            "Travel allowance ₹2,000/month. Stipend: ₹30,000/month.",
            "Travel allowance ₹2,000/month stipend ₹30,000/month",
            "Internet stipend 1,000/month stipend 30,000/month",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertEqual(info.amount, 30000, text)

    def test_display_shows_a_range_only_when_one_is_stated(self):
        single = classify_stipend("Stipend: ₹35,000/month; travel allowance 2,000/month")
        self.assertEqual(single.display_label(), "₹35,000/mo confirmed")
        self.assertNotIn("-", single.display_label())

        ranged = classify_stipend("Stipend: ₹30,000-40,000/month")
        self.assertEqual(ranged.display_label(), "₹30,000-40,000/mo confirmed")


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

    def test_unpaid_or_commission_only_beats_a_package_figure(self):
        # A CTC/annual package figure is not the stipend's own figure and must
        # never override an explicit unpaid or commission-only statement.
        for text in (
            "Unpaid internship. CTC ₹6,00,000/annum.",
            "No stipend. Annual package: ₹6,00,000.",
            "Stipend: Unpaid. Salary ₹8,00,000 per annum.",
            "commission only. Salary: 50000 per month",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, UNPAID, text)
            self.assertTrue(info.dropped, text)

    def test_conditional_stipend_is_judged_on_the_stipend_not_the_package(self):
        # A variable "up to" stipend is below the floor even though the posting
        # also quotes a large annual package; the package figure must not turn a
        # below-floor stipend into a confirmed one.
        info = classify_stipend("Stipend: up to ₹15,000/month. CTC ₹6,00,000/annum.")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(info.amount, 15000)
        self.assertTrue(info.dropped)

    def test_upper_bound_only_stipend_is_unstated_not_unpaid(self):
        # An "up to X" cap cannot confirm the floor, so it is unknown and must be
        # surfaced for verification - never dropped as unpaid.
        for text in (
            "Stipend: up to ₹50,000/month",
            "upto ₹35,000/month",
            "Stipend: up to 40k per month",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, UNSTATED, text)
            self.assertFalse(info.dropped, text)

    def test_genuine_unpaid_statements_survive_a_cross_phrase_negation(self):
        # A negation that governs a different phrase ("no stipend", "not paying")
        # must not suppress a genuine "unpaid" claim.
        for text in (
            "No stipend, unpaid internship.",
            "Not a paid role, unpaid role.",
            "We are not paying, unpaid internship.",
            "No salary, unpaid internship.",
        ):
            self.assertEqual(classify_stipend(text).state, UNPAID, text)

    def test_cue_less_monthly_stipend_beats_an_earlier_package_figure(self):
        # Both figures are cue-less; the monthly rate is the stipend, so a
        # preceding annual package figure must not win.
        info = classify_stipend("CTC ₹6,00,000/annum. ₹15,000/month")
        self.assertEqual(info.state, CONFIRMED_BELOW_FLOOR)
        self.assertEqual(info.amount, 15000)

    def test_negated_or_comparative_unpaid_does_not_beat_a_confirmed_figure(self):
        for text in (
            "We do not offer unpaid internships. Stipend: ₹30,000/month.",
            "This is a paid internship, not an unpaid one. Stipend ₹40,000/month.",
            "Unpaid roles are not offered. Salary: ₹50,000 per month.",
            "We do not offer unpaid internships. Salary ₹40,000 per month.",
            "We don't offer unpaid internships. Salary ₹40,000 per month.",
            "This isn't an unpaid role. Salary ₹40,000/month.",
            "We are no longer offering unpaid internships. Salary ₹40,000/month.",
            "The internship isn't unpaid. Pay: ₹40,000/month.",
        ):
            info = classify_stipend(text)
            self.assertEqual(info.state, CONFIRMED_GE_FLOOR, text)
            self.assertFalse(info.dropped, text)

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


class StipendStateIsNotPersistedTests(unittest.TestCase):
    """Stipend state has one definition: it is computed where it is used, so the
    postings schema must not carry a second, write-only copy of it."""

    def test_fresh_store_has_no_stipend_state_columns(self):
        store = Store(":memory:")
        try:
            columns = {row["name"] for row in store.conn.execute("PRAGMA table_info(postings)")}
            self.assertNotIn("stipend_state", columns)
            self.assertNotIn("stipend_amount", columns)
            p = posting(job_id="no-stipend-cols", title="Machine Learning Intern")
            store.upsert_posting(p, eligible=True)
            self.assertEqual(store.get_posting(p.stable_id)["title"], p.title)
        finally:
            store.close()

    def test_existing_db_with_old_stipend_columns_still_opens_and_upserts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "jobpilot.db"
            store = Store(db)
            # Simulate a DB written by the earlier revision that added them.
            store.conn.execute("ALTER TABLE postings ADD COLUMN stipend_state TEXT")
            store.conn.execute("ALTER TABLE postings ADD COLUMN stipend_amount INTEGER")
            store.conn.commit()
            store.close()

            store = Store(db)  # migration must not crash on the pre-existing columns
            try:
                p = posting(job_id="old-db", title="Machine Learning Intern")
                store.upsert_posting(p, eligible=True)
                self.assertEqual(store.get_posting(p.stable_id)["title"], p.title)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
