"""Tests for the widened discovery adapters and the typed fields they carry.

No network: every adapter's ``fetch_json`` is patched with a captured fixture so
the tests exercise URL construction, pagination and normalisation only.
"""

from __future__ import annotations

import unittest
from unittest import mock

from jobpilot.applying.applier import Applier
from jobpilot.config import Config
from jobpilot.discovery.ashby import AshbyAdapter
from jobpilot.discovery.greenhouse import GreenhouseAdapter
from jobpilot.discovery.himalayas import HimalayasAdapter
from jobpilot.discovery.lever import LeverAdapter
from jobpilot.discovery.themuse import TheMuseAdapter
from jobpilot.discovery.unstop import UnstopAdapter
from jobpilot.discovery.workable import WorkableAdapter
from jobpilot.discovery.workable_global import WorkableGlobalAdapter
from jobpilot.filtering import filter_posting, review_only_reasons
from jobpilot.http import FetchError
from jobpilot.store import Store
from jobpilot.window import classify_window
from tests.helpers import FakeAdapter, plan_for, test_config


def _source(cfg: Config, name: str, **options):
    source = cfg.sources[name]
    source.options = dict(options)
    return source


class HimalayasTests(unittest.TestCase):
    def test_normalises_typed_fields(self):
        adapter = HimalayasAdapter(_source(test_config(), "himalayas"), test_config())
        posting = adapter._normalise(
            {
                "title": "Machine Learning Intern",
                "companyName": "Aurora",
                "employmentType": "Intern",
                "locationRestrictions": ["India"],
                "description": "<p>Build LLM systems.</p>",
                "excerpt": "An ML internship.",
                "pubDate": 1790000000,
                "applicationLink": "https://himalayas.app/jobs/ml-intern",
                "guid": "https://himalayas.app/jobs/ml-intern",
                "minSalary": 10000,
                "maxSalary": 20000,
                "salaryPeriod": "monthly",
                "currency": "USD",
            }
        )
        self.assertEqual(posting.job_id, "https://himalayas.app/jobs/ml-intern")
        self.assertEqual(posting.employment_type, "Intern")
        self.assertEqual(posting.location, "India")
        self.assertIn("LLM", posting.description)
        self.assertEqual(posting.apply_url, "https://himalayas.app/jobs/ml-intern")
        self.assertIn("10000", posting.salary)
        self.assertEqual(posting.raw["attribution"], "data sourced from Himalayas")

    def test_worldwide_without_restrictions_is_remote(self):
        adapter = HimalayasAdapter(_source(test_config(), "himalayas"), test_config())
        posting = adapter._normalise({"title": "Intern", "locationRestrictions": []})
        self.assertEqual(posting.location, "Worldwide")
        self.assertIs(posting.is_remote, True)

    def test_fetch_paginates_with_page_param(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=3, keyword=""), cfg)
        pages = {
            1: [{"guid": f"g{i}", "title": "Intern", "employmentType": "Intern"} for i in range(20)],
            2: [{"guid": "g20", "title": "Intern", "employmentType": "Intern"}],
        }

        def fake(url, **kwargs):
            page = int(url.split("page=")[1].split("&")[0])
            return {"totalCount": 21, "jobs": pages.get(page, [])}

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake) as fetch:
            postings = adapter.fetch()
        self.assertEqual(len(postings), 21)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("employment_type=Intern", fetch.call_args_list[0].args[0])
        self.assertIn("country=India", fetch.call_args_list[0].args[0])

    def test_fetch_runs_typed_and_keyword_queries_and_merges(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        typed = {"guid": "typed-1", "title": "Data Intern", "employmentType": "Intern"}
        keyword = {"guid": "kw-1", "title": "Machine Learning Intern", "employmentType": "Full Time"}
        urls: list[str] = []

        def fake(url, **kwargs):
            urls.append(url)
            if "employment_type=Intern" in url:
                return {"totalCount": 1, "jobs": [typed]}
            if "q=intern" in url:
                return {"totalCount": 1, "jobs": [keyword]}
            return {"totalCount": 0, "jobs": []}

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["typed-1", "kw-1"])
        self.assertTrue(any("employment_type=Intern" in u for u in urls))
        self.assertTrue(any("q=intern" in u and "employment_type" not in u for u in urls))

    def test_scalar_keyword_issues_one_request_not_one_per_character(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1, keyword="ml intern"), cfg)
        keyword_urls: list[str] = []

        def fake(url, **kwargs):
            if "employment_type=Intern" not in url:
                keyword_urls.append(url)
            return {"totalCount": 0, "jobs": []}

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            adapter.fetch()
        self.assertEqual(len(keyword_urls), 1)
        self.assertIn("q=ml+intern", keyword_urls[0])

    def test_secondary_query_parse_error_does_not_fail_the_adapter(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        typed = {"guid": "typed-1", "title": "Data Intern", "employmentType": "Intern"}
        full_page = [
            {"guid": f"kw-{i}", "title": "ML Intern", "employmentType": "Full Time"}
            for i in range(20)
        ]

        def fake(url, **kwargs):
            if "employment_type=Intern" in url:
                return {"totalCount": 1, "jobs": [typed]}
            return {"totalCount": "unknown", "jobs": full_page}

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertIn("typed-1", [p.job_id for p in outcome.postings])

    def test_secondary_query_non_fetch_error_does_not_fail_the_adapter(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        typed = {"guid": "typed-1", "title": "Data Intern", "employmentType": "Intern"}

        def fake(url, **kwargs):
            if "employment_type=Intern" in url:
                return {"totalCount": 1, "jobs": [typed]}
            raise ValueError("malformed keyword payload")

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertEqual([p.job_id for p in outcome.postings], ["typed-1"])

    def test_fetch_deduplicates_rows_returned_by_both_queries(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        row = {"guid": "same-1", "title": "ML Intern", "employmentType": "Intern"}

        def fake(url, **kwargs):
            return {"totalCount": 1, "jobs": [row]}

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["same-1"])

    def test_secondary_query_failure_does_not_fail_the_adapter(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        typed = {"guid": "typed-1", "title": "Data Intern", "employmentType": "Intern"}

        def fake(url, **kwargs):
            if "employment_type=Intern" in url:
                return {"totalCount": 1, "jobs": [typed]}
            raise FetchError("keyword endpoint outage")

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertEqual([p.job_id for p in outcome.postings], ["typed-1"])

    def test_fetch_safe_isolates_a_source_failure(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=FetchError("board outage")):
            outcome = adapter.fetch_safe()
        self.assertFalse(outcome.ok)
        self.assertIn("board outage", outcome.error)

    def test_fulltime_tagged_ml_intern_is_discovered_and_routes_to_review(self):
        cfg = test_config()
        adapter = HimalayasAdapter(_source(cfg, "himalayas", max_pages=1), cfg)
        mis_tagged = {
            "guid": "ml-1",
            "title": "Machine Learning Intern",
            "companyName": "Aurora",
            "employmentType": "Full Time",
            "locationRestrictions": ["India"],
            "description": "<p>Machine learning internship. Python, RAG, LLMs.</p>",
            "applicationLink": "https://himalayas.app/jobs/ml-1",
        }
        urls: list[str] = []

        def fake(url, **kwargs):
            urls.append(url)
            if "employment_type=Intern" in url:
                return {"totalCount": 0, "jobs": []}
            return {"totalCount": 1, "jobs": [mis_tagged]}

        with mock.patch("jobpilot.discovery.himalayas.fetch_json", side_effect=fake):
            postings = adapter.fetch()
        self.assertTrue(any("q=intern" in u and "employment_type" not in u for u in urls))
        found = next(p for p in postings if p.job_id == "ml-1")
        self.assertEqual(found.employment_type, "Full Time")
        self.assertTrue(any("ambiguous" in r for r in review_only_reasons(found, cfg.filter)))

        store = Store(":memory:")
        try:
            applier = Applier(store, cfg, FakeAdapter(cfg), cfg.output.dir)
            outcome = applier.process(plan_for(found))
            submitted = store.has_submitted(found.stable_id)
        finally:
            store.close()
        self.assertEqual(outcome.action, "review")
        self.assertFalse(submitted)


class UnstopTests(unittest.TestCase):
    ROW = {
        "id": 1617053,
        "title": "Machine Learning Internship",
        "status": "LIVE",
        "seo_url": "https://unstop.com/internships/ml-1617053",
        "public_url": "internships/ml-1617053",
        "start_date": "2026-01-10T00:00:00+05:30",
        "end_date": "2026-06-30T00:00:00+05:30",
        "region": "online",
        "locations": [{"name": "Bengaluru"}],
        "organisation": {"name": "Aurora Labs"},
        "required_skills": [{"skill_name": "Machine Learning"}, {"skill_name": "Python"}],
        "workfunction": [{"work_function_name": "Data Science"}],
        "details": "<p>Work on ML.</p>",
        "subtype": "internships",
        "type": "jobs",
    }

    def test_normalises_row_with_dates_skills_and_org(self):
        adapter = UnstopAdapter(_source(test_config(), "unstop"), test_config())
        posting = adapter._normalise(dict(self.ROW))
        self.assertEqual(posting.job_id, "1617053")
        self.assertEqual(posting.company, "Aurora Labs")
        self.assertEqual(posting.url, "https://unstop.com/internships/ml-1617053")
        self.assertEqual(posting.employment_type, "Internship")
        self.assertIn("2026-01-10 - 2026-06-30", posting.description)
        self.assertIn("Machine Learning", posting.description)
        self.assertIn("Bengaluru", posting.location)

    def test_typed_start_end_window_is_a_verified_in_window_range(self):
        cfg = test_config()
        adapter = UnstopAdapter(_source(cfg, "unstop"), cfg)
        posting = adapter._normalise(dict(self.ROW))
        result = filter_posting(posting, cfg.filter)
        self.assertTrue(result.eligible, result.reject_text())
        self.assertEqual(result.window_label, "Jan-Jun 2026")
        self.assertEqual(result.window_confidence, 1.0)

    def test_typed_window_survives_deadline_prose_in_the_next_segment(self):
        cfg = test_config()
        adapter = UnstopAdapter(_source(cfg, "unstop"), cfg)
        row = {
            **dict(self.ROW),
            "workfunction": [],
            "details": "<p>Applications are invited from eligible candidates.</p>",
        }
        posting = adapter._normalise(row)
        self.assertIn("Applications are invited", posting.description)

        info = classify_window(posting.searchable_text(), cfg.filter, prose=posting.description)
        self.assertIs(info.overlaps, True)
        self.assertEqual(info.confidence, 1.0)

        result = filter_posting(posting, cfg.filter)
        self.assertTrue(result.eligible, result.reject_text())
        self.assertEqual(result.window_label, "Jan-Jun 2026")
        self.assertEqual(result.window_confidence, 1.0)

    def test_fetch_skips_finished_and_stops_on_last_page(self):
        cfg = test_config()
        adapter = UnstopAdapter(_source(cfg, "unstop", max_pages=5), cfg)
        payload = {
            "data": {
                "data": [dict(self.ROW), {**self.ROW, "id": 2, "status": "FINISHED"}],
                "last_page": 1,
                "per_page": 10,
            }
        }
        with mock.patch("jobpilot.discovery.unstop.fetch_json", return_value=payload) as fetch:
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["1617053"])
        self.assertEqual(fetch.call_count, 1)


class WorkableGlobalTests(unittest.TestCase):
    def test_normalises_and_paginates_with_page_token(self):
        cfg = test_config()
        adapter = WorkableGlobalAdapter(_source(cfg, "workable_global", max_pages=3), cfg)
        page1 = {
            "jobs": [
                {
                    "id": "w1",
                    "title": "ML Intern",
                    "company": {"title": "Aurora"},
                    "location": {"city": "Bengaluru", "countryName": "India"},
                    "employmentType": "Full-time",
                    "workplace": "on_site",
                    "description": "<p>ML</p>",
                    "url": "https://jobs.workable.com/view/w1",
                    "created": "2026-09-01T00:00:00Z",
                }
            ],
            "nextPageToken": "tok",
        }
        page2 = {"jobs": [{**page1["jobs"][0], "id": "w2", "url": "https://jobs.workable.com/view/w2"}], "nextPageToken": ""}

        def fake(url, **kwargs):
            return page1 if "pageToken" not in url else page2

        with mock.patch("jobpilot.discovery.workable_global.fetch_json", side_effect=fake) as fetch:
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["w1", "w2"])
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("pageToken=tok", fetch.call_args_list[1].args[0])
        self.assertEqual(postings[0].company, "Aurora")
        self.assertEqual(postings[0].employment_type, "Full-time")
        self.assertIn("India", postings[0].location)

    def test_typed_fulltime_row_is_kept_because_global_field_is_unreliable(self):
        cfg = test_config()
        adapter = WorkableGlobalAdapter(_source(cfg, "workable_global", max_pages=1), cfg)
        payload = {"jobs": [{"id": "w1", "title": "Intern", "employmentType": "Full-time"}], "nextPageToken": ""}
        with mock.patch("jobpilot.discovery.workable_global.fetch_json", return_value=payload):
            postings = adapter.fetch()
        self.assertEqual(len(postings), 1)


class TheMuseTests(unittest.TestCase):
    RESULT = {
        "id": 18552328,
        "name": "Machine Learning Intern",
        "company": {"name": "Aurora"},
        "locations": [{"name": "Bengaluru, India"}],
        "levels": [{"name": "Internship"}],
        "refs": {"landing_page": "https://www.themuse.com/jobs/aurora/ml-intern"},
        "publication_date": "2026-01-02T00:00:00Z",
        "contents": "<p>Work on ML.</p>",
    }

    def test_normalises_typed_levels(self):
        adapter = TheMuseAdapter(_source(test_config(), "themuse"), test_config())
        posting = adapter._normalise(dict(self.RESULT))
        self.assertEqual(posting.job_id, "18552328")
        self.assertEqual(posting.employment_type, "Internship")
        self.assertEqual(posting.company, "Aurora")
        self.assertEqual(posting.url, "https://www.themuse.com/jobs/aurora/ml-intern")
        self.assertIn("ML", posting.description)

    def test_fetch_uses_level_and_stops_on_page_count(self):
        cfg = test_config()
        adapter = TheMuseAdapter(_source(cfg, "themuse", max_pages=5), cfg)

        def fake(url, **kwargs):
            return {"page": 1, "page_count": 4, "results": [dict(self.RESULT)]}

        with mock.patch("jobpilot.discovery.themuse.fetch_json", side_effect=fake) as fetch:
            postings = adapter.fetch()
        # the typed page has < PAGE_SIZE rows so it stops, and the broader query
        # returns the same row; it is deduplicated by source job id.
        self.assertEqual(len(postings), 1)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("level=Internship", fetch.call_args_list[0].args[0])
        self.assertNotIn("level", fetch.call_args_list[1].args[0])

    def test_broad_query_parse_error_does_not_fail_the_adapter(self):
        cfg = test_config()
        adapter = TheMuseAdapter(_source(cfg, "themuse", max_pages=1), cfg)
        broad = [{**self.RESULT, "id": 1000 + i} for i in range(20)]

        def fake(url, **kwargs):
            if "level=Internship" in url:
                return {"page": 1, "page_count": 1, "results": [dict(self.RESULT)]}
            return {"page": 1, "page_count": "lots", "results": broad}

        with mock.patch("jobpilot.discovery.themuse.fetch_json", side_effect=fake):
            outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertIn("18552328", [p.job_id for p in outcome.postings])

    def test_broad_query_non_fetch_error_does_not_fail_the_adapter(self):
        cfg = test_config()
        adapter = TheMuseAdapter(_source(cfg, "themuse", max_pages=1), cfg)

        def fake(url, **kwargs):
            if "level=Internship" in url:
                return {"page": 1, "page_count": 1, "results": [dict(self.RESULT)]}
            raise ValueError("malformed broad payload")

        with mock.patch("jobpilot.discovery.themuse.fetch_json", side_effect=fake):
            outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertEqual([p.job_id for p in outcome.postings], ["18552328"])

    def test_fulltime_tagged_ml_intern_is_discovered_and_routes_to_review(self):
        cfg = test_config()
        adapter = TheMuseAdapter(_source(cfg, "themuse", max_pages=1), cfg)
        mis_tagged = {
            "id": 99001,
            "name": "Machine Learning Intern",
            "company": {"name": "Aurora"},
            "locations": [{"name": "Bengaluru, India"}],
            "levels": [{"name": "Full Time"}],
            "refs": {"landing_page": "https://www.themuse.com/jobs/aurora/ml-intern"},
            "publication_date": "2026-01-02T00:00:00Z",
            "contents": "<p>Machine learning internship. Python, RAG, LLMs.</p>",
        }
        urls: list[str] = []

        def fake(url, **kwargs):
            urls.append(url)
            if "level=Internship" in url:
                return {"page": 1, "page_count": 1, "results": []}
            return {"page": 1, "page_count": 1, "results": [mis_tagged]}

        with mock.patch("jobpilot.discovery.themuse.fetch_json", side_effect=fake):
            postings = adapter.fetch()
        self.assertTrue(any("location=India" in u and "level" not in u for u in urls))
        found = next(p for p in postings if p.job_id == "99001")
        self.assertEqual(found.employment_type, "Full Time")
        self.assertTrue(any("ambiguous" in r for r in review_only_reasons(found, cfg.filter)))

        store = Store(":memory:")
        try:
            applier = Applier(store, cfg, FakeAdapter(cfg), cfg.output.dir)
            outcome = applier.process(plan_for(found))
            submitted = store.has_submitted(found.stable_id)
        finally:
            store.close()
        self.assertEqual(outcome.action, "review")
        self.assertFalse(submitted)


class AdapterCoverageTests(unittest.TestCase):
    """Adapters carry each board's typed employment value but never drop a
    posting on it; the shared hard filter decides, so a genuine intern a board
    happens to tag ``FullTime`` is still surfaced and routed to review."""

    def test_lever_carries_typed_commitment_without_dropping(self):
        cfg = test_config()
        source = _source(cfg, "lever")
        source.tokens = ["acme"]
        adapter = LeverAdapter(source, cfg)
        payload = [
            {"id": "1", "text": "ML Intern", "categories": {"commitment": "Intern", "location": "India"}},
            {"id": "2", "text": "Senior Engineer", "categories": {"commitment": "Fulltime", "location": "India"}},
        ]
        with mock.patch("jobpilot.discovery.lever.fetch_json", return_value=payload) as fetch:
            postings = adapter.fetch()
        url = fetch.call_args_list[0].args[0]
        self.assertNotIn("commitment", url)
        self.assertNotIn("employment", url)
        self.assertEqual([p.job_id for p in postings], ["1", "2"])
        self.assertEqual(postings[1].employment_type, "Fulltime")

    def test_ashby_carries_typed_employment_type_without_dropping(self):
        cfg = test_config()
        source = _source(cfg, "ashby")
        source.tokens = ["acme"]
        adapter = AshbyAdapter(source, cfg)
        payload = {
            "jobs": [
                {"id": "1", "title": "Program", "employmentType": "Intern", "jobUrl": "u1"},
                {"id": "2", "title": "ML Intern", "employmentType": "Full Time", "jobUrl": "u2"},
            ]
        }
        with mock.patch("jobpilot.discovery.ashby.fetch_json", return_value=payload):
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["1", "2"])
        self.assertEqual(postings[1].employment_type, "Full Time")

    def test_greenhouse_keeps_all_rows_and_carries_typed_metadata(self):
        cfg = test_config()
        source = _source(cfg, "greenhouse")
        source.tokens = ["acme"]
        adapter = GreenhouseAdapter(source, cfg)
        payload = {
            "jobs": [
                {"id": "1", "title": "Program", "metadata": [{"name": "Employment Type", "value": "Intern"}]},
                {"id": "2", "title": "ML Intern", "metadata": [{"name": "Employment Type", "value": "FullTime"}]},
                {"id": "3", "title": "Data Intern", "metadata": []},
            ]
        }
        with mock.patch("jobpilot.discovery.greenhouse.fetch_json", return_value=payload):
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["1", "2", "3"])
        self.assertEqual(postings[1].employment_type, "FullTime")

    def test_workable_widget_carries_typed_employment_type_without_dropping(self):
        cfg = test_config()
        source = _source(cfg, "workable")
        source.tokens = ["acme"]
        adapter = WorkableAdapter(source, cfg)
        payload = {
            "name": "Acme",
            "jobs": [
                {"shortcode": "a", "title": "Program", "employment_type": "Intern"},
                {"shortcode": "b", "title": "ML Intern", "employment_type": "Full-time"},
                {"shortcode": "c", "title": "Data Intern", "employment_type": ""},
            ],
        }
        with mock.patch("jobpilot.discovery.workable.fetch_json", return_value=payload):
            postings = adapter.fetch()
        self.assertEqual([p.job_id for p in postings], ["a", "b", "c"])
        self.assertEqual(postings[1].employment_type, "Full-time")

    def test_fulltime_tagged_ml_intern_survives_discovery_and_routes_to_review(self):
        cfg = test_config()
        source = _source(cfg, "greenhouse")
        source.tokens = ["acme"]
        adapter = GreenhouseAdapter(source, cfg)
        payload = {
            "jobs": [
                {
                    "id": "7",
                    "title": "Machine Learning Intern",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/7",
                    "location": {"name": "Bengaluru, India"},
                    "content": "<p>Machine learning internship, January 2026 to June 2026. Python, RAG, LLMs.</p>",
                    "metadata": [{"name": "Employment Type", "value": "FullTime"}],
                }
            ]
        }
        with mock.patch("jobpilot.discovery.greenhouse.fetch_json", return_value=payload):
            postings = adapter.fetch()
        self.assertEqual(len(postings), 1)
        found = postings[0]
        self.assertEqual(found.employment_type, "FullTime")
        self.assertTrue(any("ambiguous" in r for r in review_only_reasons(found, cfg.filter)))

        store = Store(":memory:")
        try:
            applier = Applier(store, cfg, FakeAdapter(cfg), cfg.output.dir)
            outcome = applier.process(plan_for(found))
            submitted = store.has_submitted(found.stable_id)
        finally:
            store.close()
        self.assertEqual(outcome.action, "review")
        self.assertEqual(outcome.status, "filter_review")
        self.assertFalse(submitted)


if __name__ == "__main__":
    unittest.main()
