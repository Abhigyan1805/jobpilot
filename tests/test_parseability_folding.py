"""Tests for typographic/Unicode folding and contact-detail verification.

LaTeX renders ``'`` as U+2019 and ``--`` as U+2013, so a literal comparison
false-fails a genuinely parseable resume. Both sides of the comparison are now
folded (NFC + typographic punctuation) while the raw extraction is left intact.
The text layer must also still carry the profile's contact details and sections.
"""

from __future__ import annotations

import unicodedata
import unittest

from jobpilot.resume.parseability import check_parseability, normalize_text


class NormalizeTextTests(unittest.TestCase):
    def test_folds_curly_apostrophe_and_dashes(self):
        self.assertEqual(normalize_text("Master\u2019s"), "Master's")
        self.assertEqual(normalize_text("2016\u20132024"), "2016-2024")
        self.assertEqual(normalize_text("a\u2014b"), "a-b")
        self.assertEqual(normalize_text("a\u00a0b"), "a b")

    def test_nfc_composes_decomposed_accents(self):
        decomposed = unicodedata.normalize("NFD", "caf\u00e9")
        self.assertNotEqual(decomposed, "caf\u00e9")
        self.assertEqual(normalize_text(decomposed), "caf\u00e9")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_text("  a \n\t b  "), "a b")


class FoldedComparisonTests(unittest.TestCase):
    def test_curly_apostrophe_keyword_still_matches(self):
        ok, detail = check_parseability(
            "Education Experience Projects Technical Skills Master\u2019s degree",
            required_sections=["Education", "Experience", "Projects", "Technical Skills"],
            required_keywords=["Master's"],
        )
        self.assertTrue(ok, detail)

    def test_en_dash_date_range_keyword_matches(self):
        ok, detail = check_parseability(
            "Education Experience Projects Technical Skills 2016\u20132024",
            required_sections=["Education", "Experience", "Projects", "Technical Skills"],
            required_keywords=["2016-2024"],
        )
        self.assertTrue(ok, detail)

    def test_contact_details_are_required(self):
        text = "Education Experience Projects Technical Skills test@example.com"
        ok, detail = check_parseability(
            text,
            required_sections=["Education", "Experience", "Projects", "Technical Skills"],
            required_keywords=[],
            required_contact=["test@example.com", "1234567890"],
        )
        self.assertFalse(ok)
        self.assertIn("missing contact details", detail)
        self.assertIn("1234567890", detail)

    def test_contact_present_passes(self):
        text = "Education Experience Projects Technical Skills test@example.com 1234567890"
        ok, detail = check_parseability(
            text,
            required_sections=["Education", "Experience", "Projects", "Technical Skills"],
            required_keywords=[],
            required_contact=["test@example.com", "1234567890"],
        )
        self.assertTrue(ok, detail)
        self.assertIn("contact ok", detail)

    def test_raw_extraction_is_not_rewritten(self):
        text = "Master\u2019s 2016\u20132024"
        check_parseability(
            text,
            required_sections=[],
            required_keywords=[],
        )
        self.assertIn("\u2019", text)
        self.assertIn("\u2013", text)


if __name__ == "__main__":
    unittest.main()
