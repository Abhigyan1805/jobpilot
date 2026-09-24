"""Tests for the robots.txt gate.

The gate must be cautious: longest-match wins with ties to Disallow, a Disallow
for either ``*`` or the jobpilot agent blocks, 404 means permitted, and any
other read failure (including a soft-200 that is not a robots.txt) leaves
permission unconfirmed so the fetch never happens. Enforcement lives in the
shared fetch layer (:mod:`jobpilot.http`), which evaluates the concrete request
URL - path and query, not the host root - so a path-specific Disallow cannot be
bypassed.
"""

from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

from jobpilot import http
from jobpilot import robots as robots_mod
from jobpilot.discovery.base import SourceAdapter
from jobpilot.discovery.registry import build_adapters, discover
from jobpilot.robots import RobotsGate, allowed, is_robots_body
from tests.helpers import test_config


class RobotsBodyTests(unittest.TestCase):
    def test_empty_body_is_allow_all(self):
        self.assertTrue(is_robots_body(""))
        self.assertTrue(is_robots_body("   \n"))

    def test_directive_body_is_recognised(self):
        self.assertTrue(is_robots_body("User-agent: *\nDisallow: /private\n"))
        self.assertTrue(is_robots_body("Sitemap: https://x/sitemap.xml\n"))

    def test_html_error_page_is_not_a_robots_txt(self):
        self.assertFalse(is_robots_body("<html><body>500 error</body></html>"))


class RobotsRuleTests(unittest.TestCase):
    def test_404_body_is_permission_via_gate(self):
        gate = RobotsGate(fetch=lambda url: ("", 404))
        self.assertTrue(gate.verdict("https://example.com/jobs").allowed)

    def test_disallow_for_star_blocks(self):
        body = "User-agent: *\nDisallow: /jobs\n"
        self.assertFalse(allowed(body, "jobpilot", "/jobs"))
        self.assertFalse(allowed(body, "jobpilot", "/jobs/123"))
        self.assertTrue(allowed(body, "jobpilot", "/api/public/x"))

    def test_disallow_for_agent_blocks_even_when_star_allows(self):
        body = "User-agent: jobpilot\nDisallow: /api\n\nUser-agent: *\nAllow: /\n"
        self.assertFalse(allowed(body, "jobpilot", "/api/jobs"))
        self.assertTrue(allowed(body, "*", "/api/jobs"))

    def test_longest_match_wins(self):
        body = "User-agent: *\nDisallow: /jobs\nAllow: /jobs/public\n"
        self.assertTrue(allowed(body, "jobpilot", "/jobs/public"))
        self.assertFalse(allowed(body, "jobpilot", "/jobs/private"))

    def test_equal_specificity_tie_goes_to_disallow(self):
        body = "User-agent: *\nAllow: /x\nDisallow: /x\n"
        self.assertFalse(allowed(body, "jobpilot", "/x"))

    def test_percent_encoded_rule_matches_decoded_path(self):
        body = "User-agent: *\nDisallow: /foo%20bar\n"
        self.assertFalse(allowed(body, "jobpilot", "/foo bar"))

    def test_blank_lines_do_not_end_a_record(self):
        body = "User-agent: *\n\nDisallow: /blocked\n"
        self.assertFalse(allowed(body, "jobpilot", "/blocked"))

    def test_path_specific_disallow_does_not_block_a_clean_path(self):
        # The real himalayas.app rule: paged search results are disallowed while
        # the first page (no ``&page=``) is permitted.
        body = "User-agent: *\nDisallow: /jobs*&page=\n"
        self.assertFalse(
            allowed(
                body,
                "jobpilot",
                "/jobs/api/search?country=India&employment_type=Intern&page=1",
            )
        )
        self.assertTrue(allowed(body, "jobpilot", "/jobs/api/search?country=India"))


class RobotsGateTests(unittest.TestCase):
    def test_unreadable_robots_fails_closed(self):
        def boom(url):
            raise TimeoutError("no answer")

        gate = RobotsGate(fetch=boom)
        verdict = gate.verdict("https://example.com/jobs")
        self.assertFalse(verdict.allowed)
        self.assertIn("UNCONFIRMED", verdict.reason)

    def test_non_200_non_404_fails_closed(self):
        gate = RobotsGate(fetch=lambda url: ("", 403))
        self.assertFalse(gate.verdict("https://example.com/jobs").allowed)

    def test_soft_200_html_body_fails_closed(self):
        gate = RobotsGate(fetch=lambda url: ("<html>oops</html>", 200))
        verdict = gate.verdict("https://example.com/jobs")
        self.assertFalse(verdict.allowed)
        self.assertIn("not a robots.txt", verdict.reason)

    def test_disallow_for_agent_or_star_blocks_the_path(self):
        gate = RobotsGate(fetch=lambda url: ("User-agent: *\nDisallow: /jobs\n", 200))
        self.assertFalse(gate.verdict("https://example.com/jobs").allowed)
        self.assertTrue(gate.verdict("https://example.com/other").allowed)

    def test_path_specific_disallow_blocks_the_paged_request(self):
        gate = RobotsGate(fetch=lambda url: ("User-agent: *\nDisallow: /jobs*&page=\n", 200))
        self.assertFalse(
            gate.verdict("https://himalayas.app/jobs/api/search?country=India&page=1").allowed
        )
        self.assertTrue(gate.verdict("https://himalayas.app/jobs/api/search?country=India").allowed)

    def test_verdict_is_cached_per_host(self):
        calls = {"n": 0}

        def fetch(url):
            calls["n"] += 1
            return ("User-agent: *\nDisallow: /x\n", 200)

        gate = RobotsGate(fetch=fetch)
        gate.verdict("https://example.com/a")
        gate.verdict("https://example.com/b")
        gate.verdict("https://example.com/c")
        self.assertEqual(calls["n"], 1)


class _BytesResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RobotsFetchLayerTests(unittest.TestCase):
    """The gate is enforced in the shared fetch layer, per concrete request URL."""

    def test_disallowed_path_is_refused_even_when_host_root_is_allowed(self):
        body = "User-agent: *\nDisallow: /jobs*&page=\n"
        gate = RobotsGate(fetch=lambda url: (body, 200))
        with http.use_robots_gate(gate), mock.patch(
            "jobpilot.http.urllib.request.urlopen"
        ) as urlopen:
            with self.assertRaises(http.RobotsBlocked):
                http.fetch(
                    "https://himalayas.app/jobs/api/search?country=India&employment_type=Intern&page=1"
                )
        urlopen.assert_not_called()

    def test_allowed_path_is_fetched(self):
        body = "User-agent: *\nDisallow: /jobs*&page=\n"
        gate = RobotsGate(fetch=lambda url: (body, 200))
        with http.use_robots_gate(gate), mock.patch(
            "jobpilot.http.urllib.request.urlopen", return_value=_BytesResponse(b"ok")
        ) as urlopen:
            self.assertEqual(http.fetch("https://himalayas.app/jobs/api/search?country=India"), b"ok")
        self.assertEqual(urlopen.call_count, 1)

    def test_unreadable_robots_refuses_by_default(self):
        def boom(url):
            raise TimeoutError("no answer")

        gate = RobotsGate(fetch=boom)
        with http.use_robots_gate(gate), mock.patch(
            "jobpilot.http.urllib.request.urlopen"
        ) as urlopen:
            with self.assertRaises(http.RobotsBlocked):
                http.fetch("https://example.com/jobs")
        urlopen.assert_not_called()

    def test_no_active_gate_means_no_robots_check(self):
        with mock.patch(
            "jobpilot.http.urllib.request.urlopen", return_value=_BytesResponse(b"ok")
        ):
            self.assertEqual(http.fetch("https://example.com/jobs"), b"ok")


class _FakeAdapter(SourceAdapter):
    name = "fake"
    requires_tokens = False

    def __init__(self, *args, url: str = "https://fake.example/jobs", **kwargs):
        super().__init__(*args, **kwargs)
        self.url = url
        self.fetched = 0

    def fetch(self):
        self.fetched += 1
        http.fetch(self.url)
        return []


class RegistryGateTests(unittest.TestCase):
    def test_discover_installs_one_gate_and_checks_each_host_once(self):
        from jobpilot.discovery import registry

        cfg = test_config()
        cfg.sources = {"fake": type(cfg.sources["greenhouse"])(name="fake", enabled=True)}
        calls: list[str] = []

        def fetch(url):
            calls.append(url)
            return ("", 404)

        with mock.patch.dict(registry.ADAPTERS, {"fake": _FakeAdapter}, clear=True), mock.patch(
            "jobpilot.discovery.registry.RobotsGate",
            side_effect=lambda **kwargs: RobotsGate(fetch=fetch, **kwargs),
        ), mock.patch(
            "jobpilot.http.urllib.request.urlopen", return_value=_BytesResponse(b"ok")
        ):
            postings, outcomes = discover(cfg)

        self.assertEqual(postings, [])
        self.assertEqual([o.source for o in outcomes], ["fake"])
        self.assertEqual(calls, ["https://fake.example/robots.txt"])

    def test_discover_removes_the_gate_after_the_run(self):
        from jobpilot.discovery import registry

        cfg = test_config()
        cfg.sources = {"fake": type(cfg.sources["greenhouse"])(name="fake", enabled=True)}
        with mock.patch.dict(registry.ADAPTERS, {"fake": _FakeAdapter}, clear=True), mock.patch(
            "jobpilot.http.urllib.request.urlopen", return_value=_BytesResponse(b"ok")
        ):
            discover(cfg)
        self.assertIsNone(http.get_robots_gate())

    def test_gate_disabled_config_installs_no_gate(self):
        from jobpilot.discovery import registry

        cfg = test_config()
        cfg.robots.enabled = False
        cfg.sources = {"fake": type(cfg.sources["greenhouse"])(name="fake", enabled=True)}
        seen: dict = {}

        class _Probe(_FakeAdapter):
            def fetch(self):
                seen["gate"] = http.get_robots_gate()
                return []

        with mock.patch.dict(registry.ADAPTERS, {"fake": _Probe}, clear=True):
            discover(cfg)
        self.assertIsNone(seen["gate"])

    def test_build_adapters_needs_no_gate_argument(self):
        cfg = test_config()
        self.assertTrue(build_adapters(cfg))


class _Response:
    status = 200

    def read(self):
        return b"User-agent: *\nDisallow: /x\n"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DefaultFetchTests(unittest.TestCase):
    def test_retries_with_a_browser_agent_then_succeeds(self):
        agents: list[str] = []

        def fake_urlopen(request, timeout=None):
            agents.append(request.get_header("User-agent"))
            if len(agents) == 1:
                raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, None)
            return _Response()

        with mock.patch("jobpilot.robots.urllib.request.urlopen", side_effect=fake_urlopen):
            body, code = robots_mod._default_fetch("https://x/robots.txt", timeout=5)
        self.assertEqual(code, 200)
        self.assertIn("Disallow", body)
        self.assertEqual(len(agents), 2)
        self.assertNotEqual(agents[0], agents[1])

    def test_404_is_a_real_answer(self):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)

        with mock.patch("jobpilot.robots.urllib.request.urlopen", side_effect=fake_urlopen):
            body, code = robots_mod._default_fetch("https://x/robots.txt", timeout=5)
        self.assertEqual((body, code), ("", 404))


if __name__ == "__main__":
    unittest.main()
