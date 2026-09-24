"""Tests for the deterministic skill-gap heatmap."""

from __future__ import annotations

import json
import unittest

from jobpilot.store import Store
from jobpilot.upskill import collect_gaps, render_heatmap


def _posting_row(store, stable_id, *, score, missing):
    store.conn.execute(
        "INSERT INTO postings (stable_id, source, job_id, score, missing_keywords) VALUES (?,?,?,?,?)",
        (stable_id, "test", stable_id, score, json.dumps(missing)),
    )
    store.conn.commit()


def _application_row(store, stable_id, *, score, gaps):
    store.conn.execute(
        "INSERT INTO applications (stable_id, status, score, gaps) VALUES (?,?,?,?)",
        (stable_id, "submitted", score, json.dumps(gaps)),
    )
    store.conn.commit()


class CollectGapsTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_weights_by_one_minus_score(self):
        _posting_row(self.store, "p1", score=0.5, missing=["Kubernetes", "AWS"])
        _posting_row(self.store, "p2", score=0.8, missing=["Kubernetes"])
        gaps = {gap.skill: gap for gap in collect_gaps(self.store)}
        self.assertEqual(gaps["Kubernetes"].jobs, 2)
        self.assertAlmostEqual(gaps["Kubernetes"].weight, 0.5 + 0.2, places=5)
        self.assertAlmostEqual(gaps["AWS"].weight, 0.5, places=5)
        # Kubernetes has the higher total weight, so it ranks first.
        self.assertEqual(collect_gaps(self.store)[0].skill, "Kubernetes")

    def test_application_gaps_are_counted(self):
        _application_row(self.store, "a1", score=0.6, gaps=["MLOps"])
        gaps = {gap.skill: gap for gap in collect_gaps(self.store)}
        self.assertAlmostEqual(gaps["MLOps"].weight, 0.4, places=5)
        self.assertIn("application", gaps["MLOps"].sources)

    def test_posting_that_became_an_application_is_not_double_counted(self):
        _posting_row(self.store, "same", score=0.5, missing=["Kubernetes"])
        _application_row(self.store, "same", score=0.5, gaps=["Kubernetes"])
        gaps = {gap.skill: gap for gap in collect_gaps(self.store)}
        self.assertEqual(gaps["Kubernetes"].jobs, 1)
        self.assertIn("application", gaps["Kubernetes"].sources)
        self.assertNotIn("posting", gaps["Kubernetes"].sources)

    def test_missing_score_contributes_nothing(self):
        _posting_row(self.store, "p1", score=None, missing=["Kubernetes"])
        self.assertEqual(collect_gaps(self.store), [])

    def test_missing_gaps_field_contributes_nothing(self):
        _posting_row(self.store, "p1", score=0.5, missing=[])
        self.assertEqual(collect_gaps(self.store), [])

    def test_render_is_ranked_and_bounded(self):
        for i in range(3):
            _posting_row(self.store, f"p{i}", score=0.1 * i, missing=[f"skill-{i}"])
        text = render_heatmap(collect_gaps(self.store), limit=2)
        self.assertIn("skill-0", text)
        self.assertIn("... 1 more", text)

    def test_empty_render_is_explicit(self):
        self.assertIn("no recorded skill gaps", render_heatmap([]))


if __name__ == "__main__":
    unittest.main()
