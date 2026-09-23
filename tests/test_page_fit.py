"""Tests for PDF page-count verification and the one-page enforcement loop.

The captain's tailored resumes were silently two pages. The pipeline now
measures the compiled PDF deterministically and reduces it to the configured
page limit - tightening layout first, then dropping the least relevant content -
within bounded attempts, never inventing or rewriting a fact. When it cannot
fit, it queues the posting with the measured count and flags it on the card.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobpilot.config import default_config
from jobpilot.matching import Matcher
from jobpilot.pipeline import _FIT_VARIANTS, run_manual_pipeline
from jobpilot.present import ReviewCandidate, render_page, select_matches
from jobpilot.resume.compiler import CompileError
from jobpilot.resume.generator import ResumeGenerator
from jobpilot.resume.parseability import count_pages
from jobpilot.store import Store
from tests.helpers import mini_profile, posting, test_config

ML_JD = "Machine learning internship. Python, RAG, LLMs, evaluation."


class CountPagesTests(unittest.TestCase):
    def test_counts_form_feed_separated_pages(self):
        self.assertEqual(count_pages(""), 0)
        self.assertEqual(count_pages("single page text"), 1)
        self.assertEqual(count_pages("one\f"), 1)
        self.assertEqual(count_pages("one\ftwo\f"), 2)
        self.assertEqual(count_pages("one\ftwo"), 2)


class FactPreservationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()
        self.profile = mini_profile()
        self.generator = ResumeGenerator(self.profile, self.cfg)

    def test_cutting_drops_lowest_relevance_bullets_and_keeps_facts(self):
        p = posting(title="Machine Learning Intern", description=ML_JD)
        match = Matcher(self.profile, self.cfg).match(p)

        full = self.generator.render(p, match)
        cut = self.generator.render(p, match, drop_bullets=99)

        # Cutting only removes; every surviving bullet is verbatim profile content
        # and the no-invention validator still passes on the reduced output.
        self.assertLess(len(cut.provenance), len(full.provenance))
        self.assertEqual(self.generator.validate_content(cut), [])
        profile_bullets = set(self.profile.all_bullets)
        for item in cut.provenance:
            self.assertIn(item["original"], profile_bullets)

    def test_cutting_is_deterministic(self):
        p = posting(title="Machine Learning Intern", description=ML_JD)
        match = Matcher(self.profile, self.cfg).match(p)
        first = self.generator.render(p, match, drop_bullets=2)
        second = self.generator.render(p, match, drop_bullets=2)
        self.assertEqual(first.content_text, second.content_text)


class OnePageEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.cfg.profile.resume_page_limit = 1
        self.cfg.profile.resume_fit_attempts = 3

    def tearDown(self):
        self.tmp.cleanup()

    def _posting(self, job_id="page-fit-1"):
        return posting(
            source="internshala",
            job_id=job_id,
            title="Machine Learning Intern",
            description=ML_JD,
            location="Bengaluru, India",
        )

    @staticmethod
    def _fake_compile(tex_path, engine, timeout=120):
        pdf = Path(tex_path).with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-1.4 fake")
        return str(pdf), ""

    @staticmethod
    def _pages_from_tex(pdf_path):
        # Layout tightening (the "one-page fit" marker) is what makes it fit.
        tex = Path(pdf_path).with_suffix(".tex").read_text(encoding="utf-8")
        if "one-page fit" in tex:
            return "Education Experience Projects Technical Skills\f"
        return "Education Experience Projects Technical Skills\fpage two\f"

    def test_over_long_resume_is_reduced_to_one_page(self):
        def fake_extract(pdf_path, extractor, timeout=60):
            return self._pages_from_tex(pdf_path)

        with mock.patch("jobpilot.pipeline.compile_tex", side_effect=self._fake_compile), mock.patch(
            "jobpilot.pipeline.extract_pdf_text", side_effect=fake_extract
        ), mock.patch("jobpilot.pipeline.check_parseability", return_value=(True, "ok")):
            run_manual_pipeline(self.cfg, self._posting())

        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            rows = store.list_review("pending")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["resume_pages"], 1)
            self.assertEqual(rows[0]["resume_page_limit"], 1)
            app = store.iter_rows("SELECT * FROM applications")[0]
            self.assertNotIn("resume is", app["review_reason"] or "")
        finally:
            store.close()

    def test_bounded_attempts_fallback_flags_review_with_measured_count(self):
        def fake_extract(pdf_path, extractor, timeout=60):
            return "Education Experience Projects Technical Skills\fpage two\f"

        with mock.patch("jobpilot.pipeline.compile_tex", side_effect=self._fake_compile), mock.patch(
            "jobpilot.pipeline.extract_pdf_text", side_effect=fake_extract
        ), mock.patch("jobpilot.pipeline.check_parseability", return_value=(True, "ok")):
            run_manual_pipeline(self.cfg, self._posting("page-fit-2"))

        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            row = store.list_review("pending")[0]
            self.assertEqual(row["resume_pages"], 2)
            self.assertEqual(row["resume_page_limit"], 1)
            app = store.iter_rows("SELECT * FROM applications")[0]
            self.assertIn("resume is 2 pages, limit is 1", app["review_reason"])
        finally:
            store.close()

    def test_unreadable_variant_that_fits_is_flagged_for_review(self):
        # Every variant fits the page count, but the tightened layout drops a
        # required section from the extracted text. A fit that is unreadable
        # must not be reported as ready, and the reason must say so rather than
        # claiming the page count is over the limit.
        def fake_extract(pdf_path, extractor, timeout=60):
            return "Education Experience Projects\f"

        with mock.patch("jobpilot.pipeline.compile_tex", side_effect=self._fake_compile), mock.patch(
            "jobpilot.pipeline.extract_pdf_text", side_effect=fake_extract
        ):
            run_manual_pipeline(self.cfg, self._posting("page-fit-unreadable"))

        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            row = store.list_review("pending")[0]
            self.assertEqual(row["resume_pages"], 1)
            self.assertEqual(row["resume_page_limit"], 1)
            app = store.iter_rows("SELECT * FROM applications")[0]
            self.assertIn("unreadable", app["review_reason"])
            self.assertNotIn("resume is", app["review_reason"] or "")
        finally:
            store.close()

    def test_compile_failure_keeps_tex_matching_the_returned_resume(self):
        # A mid-ladder variant that fails to compile must not leave its own
        # source on disk: the persisted .tex has to match the resume that was
        # actually kept and whose PDF was compiled.
        calls = {"n": 0}

        def flaky_compile(tex_path, engine, timeout=120):
            calls["n"] += 1
            if calls["n"] > 1:
                raise CompileError("boom")
            pdf = Path(tex_path).with_suffix(".pdf")
            pdf.write_bytes(b"%PDF-1.4 fake")
            return str(pdf), ""

        def fake_extract(pdf_path, extractor, timeout=60):
            return self._pages_from_tex(pdf_path)

        p = self._posting("page-fit-compile-fail")
        with mock.patch("jobpilot.pipeline.compile_tex", side_effect=flaky_compile), mock.patch(
            "jobpilot.pipeline.extract_pdf_text", side_effect=fake_extract
        ), mock.patch("jobpilot.pipeline.check_parseability", return_value=(True, "ok")):
            run_manual_pipeline(self.cfg, p)

        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            app = store.iter_rows("SELECT resume_tex FROM applications")[0]
        finally:
            store.close()
        kept = Path(app["resume_tex"]).read_text(encoding="utf-8")

        profile = mini_profile()
        match = Matcher(profile, self.cfg).match(p)
        baseline = ResumeGenerator(profile, self.cfg).generate(
            p, match, self.cfg.resolve(self.cfg.output.dir)
        )
        self.assertEqual(kept, Path(baseline.tex_path).read_text(encoding="utf-8"))

    def test_default_fit_attempts_cover_every_ladder_rung(self):
        self.assertGreaterEqual(
            default_config().profile.resume_fit_attempts, len(_FIT_VARIANTS)
        )


class PresentPageBadgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.matcher = Matcher(mini_profile(), self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def _candidate(self, page_count, page_limit):
        return ReviewCandidate(
            review_id=1,
            posting=posting(title="Machine Learning Intern", description=ML_JD),
            score=0.8,
            band="shortlist",
            matched=["Python"],
            gaps=[],
            reasons=[],
            page_count=page_count,
            page_limit=page_limit,
        )

    def _render(self, candidate):
        selection = select_matches([candidate], self.matcher, self.cfg)
        return render_page(selection, self.cfg, Path(self.tmp.name) / "present").read_text(
            encoding="utf-8"
        )

    def test_over_limit_resume_is_flagged_on_the_card(self):
        html = self._render(self._candidate(2, 1))
        self.assertIn("Resume is 2 pages, limit is 1", html)
        self.assertIn("pagebadge warn", html)

    def test_one_page_resume_is_shown_as_verified(self):
        html = self._render(self._candidate(1, 1))
        self.assertIn("Resume: 1-page", html)
        self.assertIn("pagebadge ok", html)
        self.assertNotIn("pagebadge warn", html)


if __name__ == "__main__":
    unittest.main()
