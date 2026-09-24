import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

from jobpilot.config import SourceConfig, load_config
from jobpilot.discovery.base import SourceAdapter
from jobpilot.discovery.linkedin import LinkedInAdapter, parse_search_html
from jobpilot.discovery.localfile import LocalFileAdapter
from jobpilot.discovery.registry import build_adapters, discover
from jobpilot.http import FetchError
from tests.helpers import test_config

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_postings.json"
LINKEDIN_FIXTURE = Path(__file__).parent / "fixtures" / "linkedin_search.html"


class _BrokenAdapter(SourceAdapter):
    name = "broken"
    requires_tokens = False

    def fetch(self):
        raise RuntimeError("simulated board outage")


class AdapterTests(unittest.TestCase):
    def test_local_adapter_normalises_postings(self):
        cfg = test_config()
        cfg.sources["local"] = type(cfg.sources["greenhouse"])(name="local", enabled=True)
        cfg.sources["local"].options = {"path": str(DEMO)}
        outcome = LocalFileAdapter(cfg.sources["local"], cfg).fetch_safe()
        self.assertTrue(outcome.ok, outcome.error)
        self.assertEqual(len(outcome.postings), 4)
        titles = [p.title for p in outcome.postings]
        self.assertIn("Machine Learning Intern - Applied AI", titles)

    def test_source_failure_is_isolated_by_fetch_safe(self):
        cfg = test_config()
        outcome = _BrokenAdapter(cfg.sources["greenhouse"], cfg).fetch_safe()
        self.assertFalse(outcome.ok)
        self.assertIn("simulated board outage", outcome.error)

    def test_discover_with_all_sources_disabled_does_not_crash(self):
        cfg = test_config()
        for name in list(cfg.sources):
            cfg.sources[name].enabled = False
        postings, outcomes = discover(cfg)
        self.assertEqual(postings, [])
        self.assertTrue(all(o.skipped for o in outcomes))

    def test_linkedin_parser_extracts_card_fields(self):
        cards = parse_search_html(LINKEDIN_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["job_id"], "4466725363")
        self.assertIn("Internship", card["title"])
        self.assertIn("Hex Wireless", card["company"])
        self.assertIn("India", card["location"])
        self.assertIn("/jobs/view/", card["url"])

    def test_linkedin_parser_reads_every_card_despite_void_elements(self):
        # Regression: a void element (<br>/<img>) inside a card must not drift
        # the depth counter and stop the parser after the first result.
        markup = "".join(
            f"""
            <div class="base-card base-search-card job-search-card"
                 data-entity-urn="urn:li:jobPosting:{jid}">
              <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/x-{jid}"></a>
              <h3 class="base-search-card__title">Machine Learning Intern {jid}</h3>
              <h4 class="base-search-card__subtitle">Acme {jid}</h4>
              <span class="job-search-card__location">Bengaluru, India</span>
              <img src="logo.png"><br>
            </div>
            """
            for jid in ("111", "222", "333")
        )
        cards = parse_search_html(markup)
        self.assertEqual([c["job_id"] for c in cards], ["111", "222", "333"])
        self.assertTrue(all("India" in c["location"] for c in cards))

    def test_linkedin_parser_keeps_full_title_with_nested_markup(self):
        # Regression: a non-void element nested inside the title (e.g. <b>/
        # <strong> highlighting a matched keyword) must not end the capture
        # early and drop the rest of the title.
        markup = """
        <div class="base-card base-search-card job-search-card"
             data-entity-urn="urn:li:jobPosting:999">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/x-999"></a>
          <h3 class="base-search-card__title">Machine <b>Learning</b> Intern <strong>AI</strong></h3>
          <h4 class="base-search-card__subtitle">Acme</h4>
          <span class="job-search-card__location">Bengaluru, India</span>
        </div>
        """
        cards = parse_search_html(markup)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "Machine Learning Intern AI")
        self.assertEqual(cards[0]["company"], "Acme")
        self.assertEqual(cards[0]["location"], "Bengaluru, India")

    def test_linkedin_adapter_built_only_when_reader_enabled(self):
        cfg = test_config()
        cfg.linkedin.enabled = False
        self.assertNotIn("linkedin", [a.name for a in build_adapters(cfg)])
        cfg.linkedin.enabled = True
        self.assertIn("linkedin", [a.name for a in build_adapters(cfg)])

    def test_config_overrides_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                "[profile]\npath = 'p.md'\n[apply]\ndaily_cap = 3\n[filter]\nwindow_end_month = 5\n",
                encoding="utf-8",
            )
            cfg = load_config(path)
            self.assertEqual(cfg.apply.daily_cap, 3)
            self.assertEqual(cfg.filter.window_end_month, 5)
            self.assertEqual(cfg.profile.path, "p.md")
            # untouched values keep their defaults
            self.assertEqual(cfg.filter.window_start_month, 1)


def _card(jid, title="Machine Learning Intern", company="Acme", location="Bengaluru, India"):
    return (
        f'<div class="base-card base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:{jid}">'
        f'<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/x-{jid}"></a>'
        f'<h3 class="base-search-card__title">{title}</h3>'
        f'<h4 class="base-search-card__subtitle">{company}</h4>'
        f'<span class="job-search-card__location">{location}</span>'
        f"</div>"
    )


class LinkedInFetchTests(unittest.TestCase):
    """The reader runs a configurable query list, merges and dedupes by job id,
    and reports each query's contribution."""

    def _adapter(self, cfg):
        source = cfg.sources.get("linkedin") or SourceConfig(name="linkedin", enabled=True)
        cfg.sources["linkedin"] = source
        return LinkedInAdapter(source, cfg)

    @staticmethod
    def _query(url: str) -> str:
        return unquote(url).split("keywords=")[1].split("&")[0]

    def test_runs_every_query_and_dedupes_by_job_id(self):
        cfg = test_config()
        cfg.linkedin.keywords = ["machine learning intern", "AI intern"]
        cfg.linkedin.max_pages = 2
        adapter = self._adapter(cfg)

        def fake(url, **kwargs):
            if self._query(url) == "machine learning intern":
                return _card("111") + _card("222")
            return _card("222") + _card("333")  # 222 overlaps the first query

        with mock.patch("jobpilot.discovery.linkedin.fetch_text", side_effect=fake), mock.patch(
            "jobpilot.discovery.linkedin.time.sleep"
        ):
            postings = adapter.fetch()

        self.assertEqual([p.job_id for p in postings], ["111", "222", "333"])
        self.assertEqual(adapter.query_counts["keywords=machine learning intern"], 2)
        self.assertEqual(adapter.query_counts["keywords=AI intern"], 1)

    def test_a_fully_duplicate_first_page_does_not_stop_paging_a_query(self):
        # Regression: a query whose first page is entirely duplicates of an
        # earlier query must still be paged. No-new-ids on a page is not
        # evidence the query is exhausted, so its later unique ids must be
        # fetched (the previous overlap early-stop dropped them).
        cfg = test_config()
        cfg.linkedin.keywords = ["machine learning intern", "AI intern"]
        cfg.linkedin.max_pages = 2
        adapter = self._adapter(cfg)

        def fake(url, **kwargs):
            query = self._query(url)
            start = int(unquote(url).split("start=")[1].split("&")[0])
            if query == "machine learning intern":
                return _card("1") + _card("2") if start == 0 else _card("3") + _card("4")
            return _card("1") + _card("2") if start == 0 else _card("5") + _card("6")

        with mock.patch("jobpilot.discovery.linkedin.fetch_text", side_effect=fake), mock.patch(
            "jobpilot.discovery.linkedin.time.sleep"
        ):
            postings = adapter.fetch()

        self.assertEqual([p.job_id for p in postings], ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(adapter.query_counts["keywords=AI intern"], 2)

    def test_scalar_keyword_still_works_as_one_query(self):
        cfg = test_config()
        cfg.linkedin.keywords = "intern"  # legacy single-keyword config
        adapter = self._adapter(cfg)

        def fake(url, **kwargs):
            return _card("111")

        with mock.patch("jobpilot.discovery.linkedin.fetch_text", side_effect=fake), mock.patch(
            "jobpilot.discovery.linkedin.time.sleep"
        ):
            postings = adapter.fetch()

        self.assertEqual([p.job_id for p in postings], ["111"])
        self.assertEqual(adapter.query_counts, {"keywords=intern": 1})

    def test_one_query_failure_does_not_fail_the_adapter(self):
        cfg = test_config()
        cfg.linkedin.keywords = ["machine learning intern", "AI intern"]
        adapter = self._adapter(cfg)

        def fake(url, **kwargs):
            if self._query(url) == "AI intern":
                raise FetchError("query outage")
            return _card("111")

        with mock.patch("jobpilot.discovery.linkedin.fetch_text", side_effect=fake), mock.patch(
            "jobpilot.discovery.linkedin.time.sleep"
        ):
            outcome = adapter.fetch_safe()

        self.assertTrue(outcome.ok)
        self.assertEqual([p.job_id for p in outcome.postings], ["111"])
        self.assertEqual(outcome.query_counts["keywords=AI intern"], 0)
        self.assertIn("query outage", outcome.query_errors["keywords=AI intern"])
        self.assertNotIn("keywords=machine learning intern", outcome.query_errors)

    def test_all_queries_failing_raises(self):
        cfg = test_config()
        cfg.linkedin.keywords = ["machine learning intern", "AI intern"]
        adapter = self._adapter(cfg)
        with mock.patch("jobpilot.discovery.linkedin.fetch_text", side_effect=FetchError("down")), mock.patch(
            "jobpilot.discovery.linkedin.time.sleep"
        ):
            outcome = adapter.fetch_safe()
        self.assertFalse(outcome.ok)
        self.assertIn("down", outcome.error)

    def test_sign_in_wall_aborts_without_hammering_every_query(self):
        cfg = test_config()
        cfg.linkedin.keywords = ["machine learning intern", "AI intern", "data science intern"]
        adapter = self._adapter(cfg)
        with mock.patch(
            "jobpilot.discovery.linkedin.fetch_text", return_value="<html>authwall sign in</html>"
        ) as fetch, mock.patch("jobpilot.discovery.linkedin.time.sleep"):
            outcome = adapter.fetch_safe()
        self.assertFalse(outcome.ok)
        self.assertIn("sign-in wall", outcome.error)
        self.assertEqual(fetch.call_count, 1)

    def test_max_results_caps_the_merged_total(self):
        cfg = test_config()
        cfg.linkedin.keywords = ["machine learning intern", "AI intern"]
        cfg.linkedin.max_results = 2
        adapter = self._adapter(cfg)

        def fake(url, **kwargs):
            return "".join(_card(str(100 + i)) for i in range(5))

        with mock.patch("jobpilot.discovery.linkedin.fetch_text", side_effect=fake), mock.patch(
            "jobpilot.discovery.linkedin.time.sleep"
        ):
            postings = adapter.fetch()
        self.assertEqual(len(postings), 2)


class SourceReportingTests(unittest.TestCase):
    def test_per_query_counts_are_printed(self):
        import contextlib
        import io

        from jobpilot.cli import _print_source_outcomes
        from jobpilot.discovery.base import FetchOutcome
        from jobpilot.models import JobPosting
        from jobpilot.pipeline import PipelineResult

        outcome = FetchOutcome(
            source="linkedin",
            postings=[
                JobPosting(source="linkedin", job_id="1", company="Acme", title="ML Intern", url="u")
            ],
            query_counts={"keywords=machine learning intern": 7, "keywords=AI intern": 3},
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _print_source_outcomes(PipelineResult(source_outcomes=[outcome]))
        text = buf.getvalue()
        self.assertIn("keywords=machine learning intern: 7 new", text)
        self.assertIn("keywords=AI intern: 3 new", text)

    def test_failed_query_is_printed_distinctly_from_an_empty_one(self):
        import contextlib
        import io

        from jobpilot.cli import _print_source_outcomes
        from jobpilot.discovery.base import FetchOutcome
        from jobpilot.models import JobPosting
        from jobpilot.pipeline import PipelineResult

        outcome = FetchOutcome(
            source="linkedin",
            postings=[
                JobPosting(source="linkedin", job_id="1", company="Acme", title="ML Intern", url="u")
            ],
            query_counts={"keywords=machine learning intern": 7, "keywords=AI intern": 0},
            query_errors={"keywords=AI intern": "FetchError: query outage"},
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _print_source_outcomes(PipelineResult(source_outcomes=[outcome]))
        text = buf.getvalue()
        self.assertIn("keywords=machine learning intern: 7 new", text)
        self.assertIn("keywords=AI intern: FAILED (FetchError: query outage)", text)
        self.assertNotIn("keywords=AI intern: 0 new", text)


if __name__ == "__main__":
    unittest.main()
