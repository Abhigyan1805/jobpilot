"""Tests for the manual link-out channel and its safety guarantees."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from jobpilot.applying.applier import Applier
from jobpilot.cli import main
from jobpilot.config import MANUAL_ONLY_SOURCES, load_config
from jobpilot.filtering import filter_posting
from jobpilot.linkout import build_manual_posting, configured_sources, is_manual_source
from jobpilot.pipeline import PipelineResult, run_manual_pipeline
from jobpilot.store import TRANSIENT_REVIEW_REASONS, Store
from jobpilot.window import classify_window
from tests.helpers import FakeAdapter, MINI_PROFILE, plan_for, posting, test_config

IN_WINDOW = "Machine learning internship, January 2026 - June 2026. Python, RAG, LLMs, Evaluation."


class LinkOutConfigTests(unittest.TestCase):
    def test_all_eight_manual_sources_are_configured_with_links(self):
        cfg = test_config()
        names = {source.name for source in configured_sources(cfg)}
        self.assertEqual(names, set(MANUAL_ONLY_SOURCES))
        self.assertEqual(len(names), 8)
        for source in configured_sources(cfg):
            self.assertTrue(source.search_url.startswith("https://"), source.name)
            self.assertTrue(source.terms_note, source.name)

    def test_manual_sources_are_never_automated_adapters(self):
        from jobpilot.discovery.registry import ADAPTERS

        # LinkedIn is the one documented exception: an optional, read-only
        # best-effort listing reader that never authenticates or applies.
        overlap = set(ADAPTERS) & set(MANUAL_ONLY_SOURCES)
        self.assertEqual(overlap, {"linkedin"})

    def test_config_can_override_a_search_url_and_disable_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                "[link_out]\nenabled = true\n"
                "[link_out.sources.internshala]\n"
                'search_url = "https://internshala.com/internships/artificial-intelligence-internship"\n'
                "[link_out.sources.naukri]\nenabled = false\n",
                encoding="utf-8",
            )
            cfg = load_config(path)
            self.assertEqual(
                cfg.link_out.sources["internshala"].search_url,
                "https://internshala.com/internships/artificial-intelligence-internship",
            )
            self.assertFalse(cfg.link_out.sources["naukri"].enabled)
            self.assertNotIn("naukri", {s.name for s in configured_sources(cfg)})

    def test_is_manual_source(self):
        cfg = test_config()
        self.assertTrue(is_manual_source(cfg, "internshala"))
        self.assertFalse(is_manual_source(cfg, "greenhouse"))
        self.assertFalse(is_manual_source(cfg, ""))


class BuildManualPostingTests(unittest.TestCase):
    def test_rejects_non_manual_source(self):
        with self.assertRaises(ValueError):
            build_manual_posting(test_config(), source="greenhouse", url="https://x/1", title="Intern", company="A")

    def test_requires_url_and_title(self):
        cfg = test_config()
        with self.assertRaises(ValueError):
            build_manual_posting(cfg, source="internshala", url="", title="Intern", company="A")
        with self.assertRaises(ValueError):
            build_manual_posting(cfg, source="internshala", url="https://x/1", title="", company="A")

    def test_stable_id_is_derived_from_url_so_re_adds_dedupe(self):
        cfg = test_config()
        first = build_manual_posting(cfg, source="peakxv", url="https://x/1", title="Intern", company="A")
        second = build_manual_posting(cfg, source="peakxv", url="https://x/1", title="Intern", company="A")
        self.assertEqual(first.stable_id, second.stable_id)
        self.assertTrue(first.stable_id.startswith("peakxv:manual-"))
        self.assertEqual(first.apply_url, "https://x/1")

    def test_explicit_job_id_is_respected(self):
        p = build_manual_posting(
            test_config(), source="wellfound", url="https://x/2", title="Intern", company="A", job_id="abc"
        )
        self.assertEqual(p.job_id, "abc")


class ManualReviewRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_manual_source_is_routed_to_review_with_direct_link_and_never_submitted(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(
            source="internshala",
            job_id="manual-1",
            description=IN_WINDOW,
            apply_url="https://internshala.com/internship/ml-intern",
        )
        outcome = applier.process(plan_for(p))
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "manual_review")
        self.assertEqual(adapter.calls, [])
        self.assertFalse(self.store.has_submitted(p.stable_id))

        rows = self.store.list_review("pending")
        self.assertIn(p.stable_id, [r["stable_id"] for r in rows])
        packet = Path(rows[0]["packet_dir"])
        self.assertEqual(
            (packet / "apply_link.txt").read_text(encoding="utf-8").strip(),
            "https://internshala.com/internship/ml-intern",
        )

    def test_manual_route_is_a_blocking_human_reason_not_a_transient_one(self):
        adapter = FakeAdapter(self.cfg)
        applier = Applier(self.store, self.cfg, adapter, self.cfg.output.dir)
        p = posting(source="peakxv", job_id="manual-2", description=IN_WINDOW)
        applier.process(plan_for(p))
        row = self.store.submitted_or_attempted(p.stable_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["review_reason"], "manual_source")
        self.assertNotIn("manual_source", TRANSIENT_REVIEW_REASONS)


class WindowIsoRangeTests(unittest.TestCase):
    def test_iso_start_end_pair_is_an_explicit_in_window_range(self):
        cfg = test_config()
        info = classify_window("Internship window 2026-01-10 - 2026-06-30", cfg.filter)
        self.assertIs(info.overlaps, True)
        self.assertEqual(info.confidence, 1.0)

    def test_lone_iso_date_is_not_a_window_signal(self):
        cfg = test_config()
        info = classify_window("Applications close 2026-09-30", cfg.filter)
        self.assertIsNone(info.overlaps)

    def test_deadline_iso_range_in_prose_is_not_a_window_signal(self):
        cfg = test_config()
        info = classify_window(
            "Machine Learning Intern. Applications accepted 2025-08-01 through 2025-11-30.",
            cfg.filter,
        )
        self.assertIsNone(info.overlaps)

    def test_bare_employment_type_token_cannot_supply_iso_context(self):
        cfg = test_config()
        p = posting(
            job_id="employment-type-context-1",
            title="Machine Learning Intern",
            employment_type="Internship",
            description="Deadline: 2025-09-01 through 2025-11-30.",
        )
        info = classify_window(p.searchable_text(), cfg.filter, prose=p.description)
        self.assertIsNone(info.overlaps)
        result = filter_posting(p, cfg.filter)
        self.assertTrue(result.eligible, result.reject_text())

    def test_deadline_iso_range_overlapping_the_target_window_is_not_verified(self):
        cfg = test_config()
        p = posting(
            job_id="employment-type-context-2",
            title="Machine Learning Intern",
            employment_type="Internship",
            description="Deadline: 2025-02-01 through 2025-03-15.",
        )
        info = classify_window(p.searchable_text(), cfg.filter, prose=p.description)
        self.assertIsNone(info.overlaps)

    def test_application_window_phrase_is_not_read_as_the_internship_window(self):
        cfg = test_config()
        info = classify_window("The application window is 2026-01-10 - 2026-06-30.", cfg.filter)
        self.assertIsNone(info.overlaps)

    def test_deadline_iso_range_does_not_reject_an_in_window_internship(self):
        cfg = test_config()
        p = posting(
            job_id="deadline-range-1",
            description=(
                "Machine learning internship. Applications accepted 2025-08-01 through "
                "2025-11-30. Python, RAG, LLMs."
            ),
        )
        result = filter_posting(p, cfg.filter)
        self.assertTrue(result.eligible, result.reject_text())


class ManualPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(Path(self.tmp.name))
        self.pdf_dir = Path(self.tmp.name) / "pdfs"
        self.pdf_dir.mkdir()
        self._counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_compile(self, tex_path, engine, timeout=120):
        self._counter += 1
        pdf = self.pdf_dir / f"doc{self._counter}.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        return str(pdf), ""

    def test_manual_posting_is_matched_tailored_and_queued_for_review(self):
        p = build_manual_posting(
            self.cfg,
            source="internshala",
            url="https://internshala.com/internship/ml-intern",
            title="Machine Learning Intern",
            company="Aurora Labs",
            location="Bengaluru, India",
            description=IN_WINDOW + " Build RAG pipelines with Python and evaluation.",
        )
        with mock.patch("jobpilot.pipeline.compile_tex", side_effect=self._fake_compile), mock.patch(
            "jobpilot.pipeline.extract_pdf_text", return_value="Education Experience Projects Technical Skills"
        ), mock.patch(
            "jobpilot.pipeline.check_parseability", return_value=(True, "ok")
        ):
            result = run_manual_pipeline(self.cfg, p)

        self.assertEqual(result.stats["queued"], 1)
        self.assertEqual(result.stats["submitted"], 0)
        self.assertIsNotNone(result.stats["review_id"])
        self.assertTrue(result.stats["tailored"])
        packet = Path(result.stats["packet_dir"])
        self.assertTrue((packet / "packet.json").exists())
        self.assertTrue((packet / "apply_link.txt").exists())

        store = Store(self.cfg.resolve(self.cfg.output.database))
        try:
            self.assertFalse(store.has_submitted(p.stable_id))
            self.assertEqual(
                [r["stable_id"] for r in store.list_review("pending")], [p.stable_id]
            )
        finally:
            store.close()

    def test_out_of_window_manual_posting_is_rejected_not_queued(self):
        p = build_manual_posting(
            self.cfg,
            source="naukri",
            url="https://naukri.com/job/1",
            title="Machine Learning Intern",
            company="BigCorp",
            location="Bengaluru, India",
            description="Internship running September 2027 - December 2027. Python.",
        )
        result = run_manual_pipeline(self.cfg, p)
        self.assertEqual(result.stats["eligible"], 0)
        self.assertIsNone(result.stats["review_id"])


class LinkOutCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp.name) / "config.toml"
        self.config_path.write_text(
            "[profile]\n"
            f'path = "{MINI_PROFILE}"\n'
            "[output]\n"
            f'dir = "{self.tmp.name}/out"\n'
            f'database = "{self.tmp.name}/jobpilot.db"\n'
            "[link_out]\nenabled = true\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_out_list_prints_sources_and_links(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--config", str(self.config_path), "link-out", "list"])
        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn("Internshala", output)
        self.assertIn("internshala.com/internships", output)
        self.assertIn("never scraped", output)

    def test_link_out_add_invokes_manual_pipeline_and_reports_queue_id(self):
        fake = PipelineResult(
            stats={
                "review_id": 7,
                "packet_dir": "/tmp/packet",
                "apply_url": "https://internshala.com/internship/1",
                "queued": 1,
            }
        )
        buffer = io.StringIO()
        with mock.patch("jobpilot.cli.run_manual_pipeline", return_value=fake) as run, redirect_stdout(buffer):
            code = main(
                [
                    "--config",
                    str(self.config_path),
                    "link-out",
                    "add",
                    "--source",
                    "internshala",
                    "--url",
                    "https://internshala.com/internship/1",
                    "--title",
                    "ML Intern",
                    "--company",
                    "Aurora",
                ]
            )
        self.assertEqual(code, 0)
        run.assert_called_once()
        self.assertIn("queued review #7", buffer.getvalue())

    def test_link_out_add_rejects_non_manual_source(self):
        buffer = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors), mock.patch("jobpilot.cli.run_manual_pipeline") as run:
            code = main(
                [
                    "--config",
                    str(self.config_path),
                    "link-out",
                    "add",
                    "--source",
                    "greenhouse",
                    "--url",
                    "https://x/1",
                    "--title",
                    "Intern",
                    "--company",
                    "A",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("not a manual-only", errors.getvalue())
        run.assert_not_called()


class UserAddedLinkOutSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp.name) / "config.toml"
        self.config_path.write_text(
            "[profile]\n"
            f'path = "{MINI_PROFILE}"\n'
            "[output]\n"
            f'dir = "{self.tmp.name}/out"\n'
            f'database = "{self.tmp.name}/jobpilot.db"\n'
            "[link_out]\nenabled = true\n"
            "[link_out.sources.customboard]\n"
            'label = "Custom Board"\n'
            'search_url = "https://customboard.example/jobs"\n'
            'terms_note = "Terms forbid automation; link-out only."\n',
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_user_added_source_is_listed_and_recognised_as_manual(self):
        cfg = load_config(self.config_path)
        self.assertIn("customboard", {s.name for s in configured_sources(cfg)})
        self.assertTrue(is_manual_source(cfg, "customboard"))
        p = build_manual_posting(
            cfg,
            source="customboard",
            url="https://customboard.example/jobs/1",
            title="Machine Learning Intern",
            company="Aurora",
        )
        self.assertEqual(p.source, "customboard")

    def test_user_added_source_is_accepted_by_cli_add(self):
        fake = PipelineResult(
            stats={
                "review_id": 3,
                "packet_dir": "/tmp/packet",
                "apply_url": "https://customboard.example/jobs/1",
                "queued": 1,
            }
        )
        buffer = io.StringIO()
        with mock.patch("jobpilot.cli.run_manual_pipeline", return_value=fake) as run, redirect_stdout(buffer):
            code = main(
                [
                    "--config",
                    str(self.config_path),
                    "link-out",
                    "add",
                    "--source",
                    "customboard",
                    "--url",
                    "https://customboard.example/jobs/1",
                    "--title",
                    "ML Intern",
                    "--company",
                    "Aurora",
                ]
            )
        self.assertEqual(code, 0)
        run.assert_called_once()

    def test_user_added_source_postings_route_to_review(self):
        cfg = load_config(self.config_path)
        store = Store(":memory:")
        try:
            adapter = FakeAdapter(cfg)
            applier = Applier(store, cfg, adapter, cfg.output.dir)
            p = posting(
                source="customboard",
                job_id="c1",
                description=IN_WINDOW,
                apply_url="https://customboard.example/jobs/1",
            )
            outcome = applier.process(plan_for(p))
            self.assertEqual(outcome.action, "review")
            self.assertEqual(outcome.status, "manual_review")
            self.assertEqual(adapter.calls, [])
            self.assertFalse(store.has_submitted(p.stable_id))
        finally:
            store.close()


class DisabledLinkOutSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp.name) / "config.toml"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_config(self, body: str) -> None:
        self.config_path.write_text(
            "[profile]\n"
            f'path = "{MINI_PROFILE}"\n'
            "[output]\n"
            f'dir = "{self.tmp.name}/out"\n'
            f'database = "{self.tmp.name}/jobpilot.db"\n' + body,
            encoding="utf-8",
        )

    def test_add_rejects_a_source_disabled_by_the_channel_flag(self):
        self._write_config("[link_out]\nenabled = false\n")
        cfg = load_config(self.config_path)
        with self.assertRaises(ValueError):
            build_manual_posting(
                cfg, source="internshala", url="https://x/1", title="Intern", company="A"
            )

    def test_add_rejects_a_per_source_disabled_source(self):
        self._write_config("[link_out]\nenabled = true\n[link_out.sources.naukri]\nenabled = false\n")
        cfg = load_config(self.config_path)
        with self.assertRaises(ValueError):
            build_manual_posting(cfg, source="naukri", url="https://x/1", title="Intern", company="A")

    def test_cli_add_rejects_a_disabled_source(self):
        self._write_config("[link_out]\nenabled = false\n")
        buffer = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors), mock.patch(
            "jobpilot.cli.run_manual_pipeline"
        ) as run:
            code = main(
                [
                    "--config",
                    str(self.config_path),
                    "link-out",
                    "add",
                    "--source",
                    "internshala",
                    "--url",
                    "https://x/1",
                    "--title",
                    "Intern",
                    "--company",
                    "A",
                ]
            )
        self.assertEqual(code, 2)
        run.assert_not_called()

    def test_posting_from_a_disabled_source_is_still_review_only(self):
        self._write_config("[link_out]\nenabled = false\n")
        cfg = load_config(self.config_path)
        store = Store(":memory:")
        try:
            adapter = FakeAdapter(cfg)
            applier = Applier(store, cfg, adapter, cfg.output.dir)
            p = posting(source="internshala", job_id="disabled-1", description=IN_WINDOW)
            outcome = applier.process(plan_for(p))
            self.assertEqual(outcome.action, "review")
            self.assertEqual(outcome.status, "manual_review")
            self.assertEqual(adapter.calls, [])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
