"""Tests for the robots.txt gate.

The gate must be cautious: longest-match wins with ties to Disallow, a Disallow
for either ``*`` or the jobpilot agent blocks, 404 means permitted, and any
other read failure (including a soft-200 that is not a robots.txt) leaves
permission unconfirmed so the fetch never happens.
"""

from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

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

    def test_unreadable_override_permits(self):
        def boom(url):
            raise TimeoutError("no answer")

        gate = RobotsGate(fetch=boom)
        verdict = gate.verdict("https://example.com/jobs", allow_unreadable=True)
        self.assertTrue(verdict.allowed)
        self.assertIn("override", verdict.reason)

    def test_override_never_permits_a_readable_disallow(self):
        gate = RobotsGate(fetch=lambda url: ("User-agent: *\nDisallow: /jobs\n", 200))
        verdict = gate.verdict("https://example.com/jobs", allow_unreadable=True)
        self.assertFalse(verdict.allowed)

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


class _CountingAdapter(SourceAdapter):
    name = "counting"
    requires_tokens = False
    hosts = ("blocked.example",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fetched = 0

    def fetch(self):
        self.fetched += 1
        return []


class FetchSafeGateTests(unittest.TestCase):
    def test_gate_failure_skips_the_fetch(self):
        cfg = test_config()
        gate = RobotsGate(fetch=lambda url: ("User-agent: *\nDisallow: /\n", 200))
        adapter = _CountingAdapter(cfg.sources["greenhouse"], cfg, robots=gate)
        outcome = adapter.fetch_safe()
        self.assertTrue(outcome.skipped)
        self.assertIn("robots gate", outcome.error)
        self.assertEqual(adapter.fetched, 0)

    def test_gate_pass_allows_the_fetch(self):
        cfg = test_config()
        gate = RobotsGate(fetch=lambda url: ("", 404))
        adapter = _CountingAdapter(cfg.sources["greenhouse"], cfg, robots=gate)
        outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertEqual(adapter.fetched, 1)

    def test_no_gate_means_no_robots_call(self):
        cfg = test_config()
        adapter = _CountingAdapter(cfg.sources["greenhouse"], cfg)
        outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok)
        self.assertEqual(adapter.fetched, 1)

    def test_configured_source_override_permits_an_unreadable_robots(self):
        def boom(url):
            raise TimeoutError("no answer")

        cfg = test_config()
        cfg.robots.allow_unreadable_sources = ["counting"]
        gate = RobotsGate(fetch=boom)
        adapter = _CountingAdapter(cfg.sources["greenhouse"], cfg, robots=gate)
        outcome = adapter.fetch_safe()
        self.assertTrue(outcome.ok, outcome.error)
        self.assertEqual(adapter.fetched, 1)

    def test_override_does_not_permit_a_readable_disallow(self):
        cfg = test_config()
        cfg.robots.allow_unreadable_sources = ["counting"]
        gate = RobotsGate(fetch=lambda url: ("User-agent: *\nDisallow: /\n", 200))
        adapter = _CountingAdapter(cfg.sources["greenhouse"], cfg, robots=gate)
        outcome = adapter.fetch_safe()
        self.assertTrue(outcome.skipped)
        self.assertEqual(adapter.fetched, 0)

    def test_default_config_overrides_ashby_only(self):
        cfg = test_config()
        self.assertIn("ashby", cfg.robots.allow_unreadable_sources)


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


class _FakeAdapter(SourceAdapter):
    name = "fake"
    requires_tokens = False
    hosts = ("fake.example",)

    def fetch(self):
        return []


class RegistryGateTests(unittest.TestCase):
    def test_build_adapters_shares_the_given_gate(self):
        from jobpilot.discovery import registry

        cfg = test_config()
        cfg.sources["fake"] = type(cfg.sources["greenhouse"])(name="fake", enabled=True)
        gate = RobotsGate(fetch=lambda url: ("", 404))
        with mock.patch.dict(registry.ADAPTERS, {"fake": _FakeAdapter}, clear=False):
            adapters = registry.build_adapters(cfg, robots=gate)
        fakes = [a for a in adapters if a.name == "fake"]
        self.assertEqual(len(fakes), 1)
        self.assertIs(fakes[0].robots, gate)

    def test_discover_creates_one_gate_and_checks_each_host_once(self):
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
        ):
            postings, outcomes = discover(cfg)

        self.assertEqual(postings, [])
        self.assertEqual([o.source for o in outcomes], ["fake"])
        self.assertEqual(calls, ["https://fake.example/robots.txt"])

    def test_gate_disabled_config_builds_adapters_without_a_gate(self):
        cfg = test_config()
        cfg.robots.enabled = False
        adapters = build_adapters(cfg)
        self.assertTrue(adapters)
        self.assertTrue(all(a.robots is None for a in adapters))


if __name__ == "__main__":
    unittest.main()
