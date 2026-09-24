"""Tests for the ``jobpilot present`` review surface and its selection rules.

The selection must include genuine technical / AI-ML / data roles and exclude
unrelated internships outright, using the pipeline's own role-relevance and
matched-skill data, configurable through ``[present]``. The renderer must copy
the tailored PDFs beside a self-contained page and make the safety state visible.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from jobpilot.cli import main
from jobpilot.matching import Matcher
from jobpilot.models import ApplicationPlan, GeneratedCoverLetter, GeneratedResume
from jobpilot.present import (
    ReviewCandidate,
    SelectionResult,
    build_candidates,
    render_page,
    run_present,
    select_matches,
    title_is_excluded,
)
from jobpilot.store import Store
from tests.helpers import MINI_PROFILE, mini_profile, plan_for, posting, strong_match, test_config

ML_JD = "Machine learning internship. Python, RAG, LLMs, evaluation."


def candidate(
    p,
    *,
    matched=(),
    gaps=(),
    score=0.7,
    band="shortlist",
    resume="",
    cover="",
    review_category="",
    review_reason="",
):
    return ReviewCandidate(
        review_id=1,
        posting=p,
        score=score,
        band=band,
        matched=list(matched),
        gaps=list(gaps),
        reasons=[],
        resume_pdf=resume,
        cover_pdf=cover,
        review_category=review_category,
        review_reason=review_reason,
    )


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()
        self.matcher = Matcher(mini_profile(), self.cfg)

    def test_technical_included_and_nontechnical_excluded(self):
        technical = candidate(
            posting(title="Machine Learning Intern", description=ML_JD),
            matched=["Python", "RAG"],
        )
        nontechnical = candidate(
            posting(
                job_id="design-1",
                title="Graphic Design Intern",
                description="Graphic design internship. Create brand visuals and social media assets.",
            ),
            matched=["Communication"],
        )
        result = select_matches([nontechnical, technical], self.matcher, self.cfg)

        self.assertEqual([m.candidate.title for m in result.included], ["Machine Learning Intern"])
        self.assertIn("Graphic Design Intern", [e.candidate.title for e in result.excluded])
        self.assertTrue(result.borderline == [])

    def test_nontechnical_title_excluded_even_when_it_name_drops_ml(self):
        # A marketing role that mentions machine learning would otherwise clear
        # the technical floor on the title hit; the role exclusion must win.
        p = posting(
            title="Machine Learning Marketing Intern",
            description="Own marketing campaigns. Machine learning and Python are nice to have.",
        )
        result = select_matches([candidate(p, matched=["Python"])], self.matcher, self.cfg)
        self.assertEqual(result.included, [])
        self.assertIn("marketing", result.excluded[0].reason)

    def test_research_domain_needs_a_core_skill(self):
        # "Research" alone is too broad: a research internship that matches no
        # core technical skill is not a technical role, but one that matches a
        # core skill is.
        soft_research = candidate(
            posting(
                job_id="research-soft",
                title="Research Intern",
                description="Research internship in design and brand strategy.",
            ),
            matched=["Communication"],
        )
        technical_research = candidate(
            posting(
                job_id="research-tech",
                title="Research Intern",
                description="Research internship. Machine learning, statistics and Python.",
            ),
            matched=["Machine Learning", "Statistics"],
        )
        result = select_matches([soft_research, technical_research], self.matcher, self.cfg)

        included = [m.candidate.posting.job_id for m in result.included]
        excluded = [e.candidate.posting.job_id for e in result.excluded]
        self.assertIn("research-tech", included)
        self.assertIn("research-soft", excluded)

    def test_borderline_fallback_shown_only_when_nothing_qualifies(self):
        technical = candidate(
            posting(title="Machine Learning Intern", description=ML_JD),
            matched=["Python"],
        )

        # Raise the floor: nothing qualifies, so the technical match is shown
        # as borderline with an explanatory note instead of an empty page.
        strict = test_config(present={"min_role_relevance": 0.99})
        result = select_matches([technical], Matcher(mini_profile(), strict), strict)
        self.assertEqual(result.included, [])
        self.assertEqual(len(result.borderline), 1)
        self.assertTrue(result.borderline[0].borderline)
        self.assertIn("below", result.borderline[0].borderline_note)

        # With a qualifying match present, borderline is suppressed (no padding).
        borderline_only = candidate(
            posting(
                job_id="border-1",
                title="Data Intern",
                description="Machine learning, deep learning, NLP and PyTorch.",
            ),
            matched=["Python"],
        )
        result = select_matches([technical, borderline_only], self.matcher, self.cfg)
        self.assertEqual(len(result.included), 1)
        self.assertEqual(result.borderline, [])

    def test_min_role_relevance_is_configurable(self):
        technical = candidate(
            posting(title="Machine Learning Intern", description=ML_JD),
            matched=["Python"],
        )
        lenient = test_config(present={"min_role_relevance": 0.2})
        result = select_matches([technical], Matcher(mini_profile(), lenient), lenient)
        self.assertEqual(len(result.included), 1)

    def test_linkout_and_linkedin_routes_are_review_only(self):
        manual = candidate(
            posting(source="internshala", title="Machine Learning Intern", description=ML_JD),
            matched=["Python"],
        )
        linkedin = candidate(
            posting(source="linkedin", job_id="li-1", title="Machine Learning Intern", description=ML_JD),
            matched=["Python"],
        )
        result = select_matches([manual, linkedin], self.matcher, self.cfg)
        routes = {m.candidate.posting.source: m.route for m in result.included}
        self.assertEqual(routes["internshala"], "linkout")
        self.assertEqual(routes["linkedin"], "linkedin")

    def test_strong_band_route_reflects_stored_review_category(self):
        technical = posting(title="Machine Learning Intern", description=ML_JD)

        # Queued only because auto-apply was off: with auto-apply armed the next
        # run can submit it, so it stays auto-apply eligible.
        transient = candidate(
            technical,
            matched=["Python"],
            band="strong",
            review_category="config",
            review_reason="auto-apply disabled by config",
        )
        # Queued for an unconfirmed window: a blocking route, never auto-applied.
        blocking = candidate(
            posting(job_id="blocking", title="Machine Learning Intern", description=ML_JD),
            matched=["Python"],
            band="strong",
            review_category="window",
            review_reason="Jan-Jun window unconfirmed; review before applying",
        )
        result = select_matches([transient, blocking], self.matcher, self.cfg)
        routes = {m.candidate.posting.job_id: m for m in result.included}

        self.assertEqual(routes["1"].route, "auto")
        self.assertEqual(routes["1"].route_label, "Auto-apply eligible")
        self.assertEqual(routes["blocking"].route, "review")
        self.assertNotIn("Auto-apply eligible", routes["blocking"].route_label)
        self.assertIn("unconfirmed", routes["blocking"].safety_detail)

    def test_title_exclusion_helper_and_config(self):
        self.assertEqual(title_is_excluded("Graphic Designer", ["designer"]), "designer")
        self.assertEqual(title_is_excluded("Graphic Design Intern", ["graphic design"]), "graphic design")
        self.assertEqual(title_is_excluded("HR Intern", ["hr"]), "hr")
        self.assertEqual(title_is_excluded("Machine Learning Intern", ["design"]), "")

        cfg = test_config(present={"exclude_terms": ["robotics"]})
        self.assertEqual(title_is_excluded("Robotics Intern", cfg.present.exclude_terms), "robotics")

    def test_colliding_words_do_not_exclude_technical_titles(self):
        # "visual", "operations" and "design" collide with genuine technical
        # vocabulary; the exclusions are phrase-based so these roles survive.
        for title in (
            "Data Visualization Intern",
            "Machine Learning Operations Intern",
            "AI System Design Intern",
        ):
            self.assertEqual(title_is_excluded(title, self.cfg.present.exclude_terms), "")

    def test_colliding_word_titles_are_selected_as_technical(self):
        cfg = test_config(present={"min_role_relevance": 0.4, "borderline_role_relevance": 0.3})
        matcher = Matcher(mini_profile(), cfg)
        candidates = [
            candidate(
                posting(job_id="viz", title="Data Visualization Intern", description=ML_JD),
                matched=["Python", "RAG"],
            ),
            candidate(
                posting(job_id="mlops", title="Machine Learning Operations Intern", description=ML_JD),
                matched=["Python"],
            ),
            candidate(
                posting(job_id="sys-design", title="AI System Design Intern", description=ML_JD),
                matched=["Python"],
            ),
        ]
        result = select_matches(candidates, matcher, cfg)
        self.assertEqual(
            sorted(m.candidate.posting.job_id for m in result.included),
            ["mlops", "sys-design", "viz"],
        )


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.matcher = Matcher(mini_profile(), self.cfg)
        self.resume = Path(self.tmp.name) / "resume.pdf"
        self.cover = Path(self.tmp.name) / "cover.pdf"
        self.resume.write_bytes(b"%PDF-1.4 tailored resume")
        self.cover.write_bytes(b"%PDF-1.4 tailored cover")

    def tearDown(self):
        self.tmp.cleanup()

    def _selection(self) -> SelectionResult:
        technical = candidate(
            posting(
                title="Machine Learning Intern",
                description=ML_JD,
                apply_url="https://example.com/apply/ml",
            ),
            matched=["Python", "RAG"],
            gaps=["Kubernetes"],
            score=0.8,
            band="strong",
            resume=str(self.resume),
            cover=str(self.cover),
        )
        return select_matches([technical], self.matcher, self.cfg)

    def test_render_writes_self_contained_page_with_copied_pdfs(self):
        selection = self._selection()
        index = render_page(selection, self.cfg, Path(self.tmp.name) / "present")
        html = index.read_text(encoding="utf-8")

        self.assertIn("Not submitted", html)
        self.assertIn("https://example.com/apply/ml", html)
        self.assertIn("Machine Learning Intern", html)
        self.assertIn("Kubernetes", html)  # gaps are shown, never inserted
        self.assertIn("assets/", html)

        copied = sorted((Path(self.tmp.name) / "present" / "assets").rglob("*.pdf"))
        self.assertEqual([p.name for p in copied], ["cover_letter.pdf", "resume.pdf"])
        self.assertTrue(all(p.read_bytes().startswith(b"%PDF") for p in copied))

    def test_render_empty_selection_says_so_honestly(self):
        index = render_page(SelectionResult(), self.cfg, Path(self.tmp.name) / "present")
        html = index.read_text(encoding="utf-8")
        self.assertIn("No technical matches to show", html)
        self.assertIn("Nothing was submitted", html)

    def test_stale_pdf_path_renders_missing_fallback_not_broken_iframe(self):
        gone = candidate(
            posting(title="Machine Learning Intern", description=ML_JD),
            matched=["Python"],
            resume=str(Path(self.tmp.name) / "gone-resume.pdf"),
            cover=str(Path(self.tmp.name) / "gone-cover.pdf"),
        )
        selection = select_matches([gone], self.matcher, self.cfg)
        index = render_page(selection, self.cfg, Path(self.tmp.name) / "present")
        html = index.read_text(encoding="utf-8")

        self.assertIn("No resume PDF was produced.", html)
        self.assertIn("No cover letter PDF was produced.", html)
        self.assertNotIn("<iframe", html)

    def test_strong_band_window_review_is_labelled_review_only(self):
        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            p = posting(job_id="window-1", title="Machine Learning Intern", description=ML_JD)
            store.upsert_posting(p, eligible=True)
            match = strong_match()
            store.save_match(p.stable_id, match, eligible=True, reject_reasons=[])
            plan = plan_for(p, match)
            store.create_application(
                plan,
                status="manual_required",
                mode="review",
                review_category="window",
                review_reason="Jan-Jun window unconfirmed; review before applying",
            )
            store.enqueue_review(plan, packet_dir="")
            candidates = build_candidates(store)
        finally:
            store.close()

        selection = select_matches(candidates, self.matcher, self.cfg)
        self.assertEqual(len(selection.included), 1)
        route = selection.included[0]
        self.assertEqual(route.route, "review")
        self.assertNotIn("Auto-apply eligible", route.route_label)
        self.assertIn("unconfirmed", route.safety_detail)

        index = render_page(selection, self.cfg, Path(self.tmp.name) / "present")
        html = index.read_text(encoding="utf-8")
        self.assertNotIn("Auto-apply eligible", html)
        self.assertIn("unconfirmed", html)

    def test_run_present_reads_the_store_and_writes_the_page(self):
        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            p = posting(job_id="e2e-1", title="Machine Learning Intern", description=ML_JD)
            store.upsert_posting(p, eligible=True)
            match = Matcher(mini_profile(), self.cfg).match(p)
            plan = ApplicationPlan(posting=p, match=match)
            plan.resume = GeneratedResume(pdf_path=str(self.resume))
            plan.cover = GeneratedCoverLetter(pdf_path=str(self.cover))
            store.enqueue_review(plan, packet_dir="")
        finally:
            store.close()

        index, selection = run_present(self.cfg, out_dir_override=str(Path(self.tmp.name) / "present"))
        self.assertTrue(index.exists())
        self.assertEqual(len(selection.included), 1)
        self.assertIn("Machine Learning Intern", index.read_text(encoding="utf-8"))


class PresentCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp.name) / "config.toml"
        self.config_path.write_text(
            "[profile]\n"
            f'path = "{MINI_PROFILE}"\n'
            "[output]\n"
            f'dir = "{self.tmp.name}/out"\n'
            f'database = "{self.tmp.name}/jobpilot.db"\n',
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_present_cli_reports_counts_and_output_path(self):
        selection = SimpleNamespace(included=[1, 2], borderline=[], excluded=[3, 4, 5])
        fake = (Path(self.tmp.name) / "out" / "present" / "index.html", selection)
        buffer = io.StringIO()
        with mock.patch("jobpilot.cli.run_present", return_value=fake) as run, redirect_stdout(buffer):
            code = main(["--config", str(self.config_path), "present"])

        self.assertEqual(code, 0)
        run.assert_called_once()
        output = buffer.getvalue()
        self.assertIn("presented 2 technical match(es)", output)
        self.assertIn("excluded 3", output)
        self.assertIn("index.html", output)


if __name__ == "__main__":
    unittest.main()
