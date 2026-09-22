import tempfile
import unittest
from pathlib import Path

from jobpilot.config import load_config
from jobpilot.discovery.base import SourceAdapter
from jobpilot.discovery.linkedin import parse_search_html
from jobpilot.discovery.localfile import LocalFileAdapter
from jobpilot.discovery.registry import discover
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


if __name__ == "__main__":
    unittest.main()
