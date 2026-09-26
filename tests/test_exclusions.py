"""Tests for the already-applied exclusion list.

The list is a presentation/selection filter, never a deletion: it matches a
re-discovery of the same posting case-insensitively on company+title and on url,
and the shipped ``data/applied-postings.toml`` carries the 45 from the current
review page.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobpilot.config import load_config
from jobpilot.exclusions import ExclusionList, _norm_url
from jobpilot.matching import Matcher
from jobpilot.present import ReviewCandidate, select_matches
from tests.helpers import MINI_PROFILE, MINI_STYLE, mini_profile, posting, test_config

ML_JD = "Machine learning internship. Python, RAG, LLMs, evaluation."


def candidate(p) -> ReviewCandidate:
    return ReviewCandidate(
        review_id=1, posting=p, score=0.7, band="shortlist", matched=["Python"], gaps=[], reasons=[]
    )


def _write_list(tmp: str, body: str) -> str:
    path = Path(tmp) / "applied.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


class ExclusionMatchTests(unittest.TestCase):
    def test_company_and_title_match_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp,
                '[[applied]]\ncompany = "Rubrik Job Board"\n'
                'title = "Software Engineer - Winter Intern"\n',
            )
            entries = ExclusionList.load(path)
        match = entries.match(
            posting(company="rubrik job board", title="software engineer - winter intern")
        )
        self.assertIsNotNone(match)

    def test_company_title_whitespace_is_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp, '[[applied]]\ncompany = "PrepLinc AI"\ntitle = "AI/ML  Application Developer Internship"\n'
            )
            entries = ExclusionList.load(path)
        match = entries.match(
            posting(company=" preplinc ai ", title="AI/ML Application Developer Internship")
        )
        self.assertIsNotNone(match)

    def test_url_match_ignores_case_and_trailing_slash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp,
                '[[applied]]\nurl = "https://unstop.com/internships/example-1760453"\n',
            )
            entries = ExclusionList.load(path)
        p = posting(source="unstop", job_id="x")
        p.url = "https://Unstop.com/internships/example-1760453/"
        self.assertIsNotNone(entries.match(p))

    def test_stable_id_and_source_job_id_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp, '[[applied]]\nsource = "unstop"\njob_id = "1760453"\n'
            )
            entries = ExclusionList.load(path)
        p = posting(source="unstop", job_id="1760453")
        self.assertIsNotNone(entries.match(p))

    def test_unrelated_posting_is_not_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp, '[[applied]]\ncompany = "Rubrik Job Board"\ntitle = "Software Engineer"\n'
            )
            entries = ExclusionList.load(path)
        self.assertIsNone(entries.match(posting(company="Other Co", title="Machine Learning Intern")))

    def test_missing_or_blank_file_means_no_exclusions(self):
        self.assertEqual(ExclusionList.load("").count, 0)
        self.assertEqual(ExclusionList.load("/nonexistent/applied.toml").count, 0)

    def test_norm_url_drops_query_and_fragment(self):
        self.assertEqual(
            _norm_url("https://Unstop.com/x/y/?a=1#frag"),
            "https://unstop.com/x/y",
        )


class ShippedListTests(unittest.TestCase):
    def test_shipped_list_has_the_45_applied_postings(self):
        path = Path(__file__).resolve().parent.parent / "data" / "applied-postings.toml"
        entries = ExclusionList.load(path)
        self.assertEqual(entries.count, 45)
        # A known member of the page is excluded by company+title even though its
        # stable id would differ on re-discovery.
        self.assertIsNotNone(
            entries.match(
                posting(
                    source="unstop",
                    company="Rubrik Job Board",
                    title="Software Engineer - Winter Intern",
                )
            )
        )


class SelectionExclusionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = test_config()
        self.matcher = Matcher(mini_profile(), self.cfg)

    def test_select_matches_drops_excluded_postings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp,
                '[[applied]]\ncompany = "Acme"\ntitle = "Machine Learning Intern"\n',
            )
            cfg = test_config(filt={"exclude_file": path})
            matcher = Matcher(mini_profile(), cfg)
            c = candidate(
                posting(company="Acme", title="Machine Learning Intern", description=ML_JD)
            )
            result = select_matches([c], matcher, cfg)
        self.assertEqual(result.included, [])
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("already applied", result.excluded[0].reason)

    def test_select_matches_still_includes_a_non_excluded_posting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_list(
                tmp, '[[applied]]\ncompany = "Someone Else"\ntitle = "Marketing Intern"\n'
            )
            cfg = test_config(filt={"exclude_file": path})
            matcher = Matcher(mini_profile(), cfg)
            c = candidate(
                posting(company="Acme", title="Machine Learning Intern", description=ML_JD)
            )
            result = select_matches([c], matcher, cfg)
        self.assertEqual(len(result.included), 1)


class DefaultExclusionFileTests(unittest.TestCase):
    """The shipped applied-list is active through the default config key."""

    def _config(self, tmp: str, body: str = ""):
        cfg_path = Path(tmp) / "config.toml"
        cfg_path.write_text(
            body + '[output]\ndir = "out"\ndatabase = ":memory:"\n', encoding="utf-8"
        )
        cfg = load_config(cfg_path)
        cfg.profile.path = str(MINI_PROFILE)
        cfg.profile.style_template = str(MINI_STYLE)
        return cfg

    def _shipped_list(self, tmp: str) -> None:
        data = Path(tmp) / "data"
        data.mkdir()
        (data / "applied-postings.toml").write_text(
            '[[applied]]\ncompany = "Acme"\ntitle = "Machine Learning Intern"\n',
            encoding="utf-8",
        )

    def test_config_without_the_key_uses_the_shipped_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._shipped_list(tmp)
            cfg = self._config(tmp)
            matcher = Matcher(mini_profile(), cfg)
            c = candidate(
                posting(company="Acme", title="Machine Learning Intern", description=ML_JD)
            )
            result = select_matches([c], matcher, cfg)
        self.assertEqual(result.included, [])
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("already applied", result.excluded[0].reason)

    def test_explicit_empty_string_disables_the_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._shipped_list(tmp)
            cfg = self._config(tmp, '[filter]\nexclude_file = ""\n')
            matcher = Matcher(mini_profile(), cfg)
            c = candidate(
                posting(company="Acme", title="Machine Learning Intern", description=ML_JD)
            )
            result = select_matches([c], matcher, cfg)
        self.assertEqual(len(result.included), 1)


if __name__ == "__main__":
    unittest.main()
