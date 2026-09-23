import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobpilot.matching import Matcher
from jobpilot.models import GeneratedResume, KeywordCoverage, MatchResult
from jobpilot.lexicon import present_surface_forms
from jobpilot.pipeline import _run_parseability
from jobpilot.profile import load_profile, parse_profile_text
from jobpilot.resume.compiler import compile_tex
from jobpilot.resume.generator import ResumeGenerator
from jobpilot.resume.parseability import (
    TextExtractionError,
    check_parseability,
    extract_pdf_text,
)
from tests.helpers import posting, test_config

REAL_PROFILE = "/mnt/d/LaTeX/resume/PROFILE.md"
REAL_STYLE = "/mnt/d/LaTeX/resume/Abhigyan_Resume_AI_ML.tex"
REAL_ENGINE = "/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdflatex.exe"
REAL_PDFTOTEXT = "/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdftotext.exe"

_HAS_TOOLCHAIN = all(os.path.exists(p) for p in (REAL_PROFILE, REAL_STYLE, REAL_ENGINE, REAL_PDFTOTEXT))


class ExtractPdfTextInvocationTests(unittest.TestCase):
    """The extractor must run with cwd + a relative filename and read stdout.

    An absolute Linux path passed as an argument is not translated for a Windows
    ``pdftotext.exe`` launched from WSL, so the extractor cannot open it. This
    guards the compiler-style invocation without needing the real toolchain.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "resume.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 dummy")

    def tearDown(self):
        self.tmp.cleanup()

    def test_invokes_relative_filename_from_pdf_directory_and_reads_stdout(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Education Experience Projects\n", stderr=""
        )
        with mock.patch("jobpilot.resume.parseability.subprocess.run", return_value=completed) as run:
            text = extract_pdf_text(str(self.pdf), "pdftotext")

        self.assertEqual(text, "Education Experience Projects\n")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["pdftotext", "-layout", "resume.pdf", "-"])
        self.assertEqual(kwargs["cwd"], str(self.pdf.parent))
        self.assertNotIn(str(self.pdf), args[0])

    def test_raises_when_extractor_produces_no_output(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with mock.patch("jobpilot.resume.parseability.subprocess.run", return_value=completed):
            with self.assertRaises(TextExtractionError):
                extract_pdf_text(str(self.pdf), "pdftotext")

    @unittest.skipUnless(os.name == "posix", "fake extractor requires a POSIX executable")
    def test_non_utf8_output_is_replaced_not_raised(self):
        extractor = Path(self.tmp.name) / "fake_extractor"
        extractor.write_text(
            f"#!{sys.executable}\nimport sys\nsys.stdout.buffer.write(b'caf\\xe9\\n')\n"
        )
        extractor.chmod(0o755)

        text = extract_pdf_text(str(self.pdf), str(extractor))

        self.assertEqual(text, "caf\ufffd\n")


@unittest.skipUnless(_HAS_TOOLCHAIN, "real LaTeX toolchain not available")
class TailoringCompileTests(unittest.TestCase):
    def test_tailored_resume_compiles_and_is_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = test_config(Path(tmp))
            cfg.profile.path = REAL_PROFILE
            cfg.profile.style_template = REAL_STYLE
            cfg.profile.pdflatex = REAL_ENGINE
            cfg.profile.pdftotext = REAL_PDFTOTEXT

            profile = load_profile(REAL_PROFILE)
            gen = ResumeGenerator(profile, cfg)
            p = posting(
                company="Aurora Labs",
                title="Machine Learning Intern",
                location="Bengaluru, India",
                description=(
                    "Machine learning internship, January 2027 - June 2027. "
                    "Python, RAG, LLM, evaluation, statistics, forecasting, SQL, data analysis."
                ),
            )
            match = Matcher(profile, cfg).match(p)
            resume = gen.generate(p, match, tmp)
            pdf_path, _log = compile_tex(resume.tex_path, REAL_ENGINE)
            self.assertTrue(Path(pdf_path).exists())

            text = extract_pdf_text(pdf_path, REAL_PDFTOTEXT)
            ok, detail = check_parseability(
                text,
                required_sections=["Education", "Experience", "Projects", "Technical Skills"],
                required_keywords=match.coverage.matched,
                min_keyword_survival=0.5,
            )
            self.assertTrue(ok, detail)

    def test_invented_number_fails_validator_against_real_profile(self):
        from jobpilot.facts import FactValidator

        profile = load_profile(REAL_PROFILE)
        validator = FactValidator(profile.raw_text)
        self.assertFalse(validator.is_clean("Scaled systems to 999999 users"))


class ParseabilitySurfaceFormTests(unittest.TestCase):
    """Alias-only canonical terms must not fail the PDF parseability check.

    The no-invention generator can only emit words present in the profile, so a
    canonical term the profile supports only through an alias ("Communication"
    via "cross-functional") must be checked as that surface form.
    """

    def test_surface_forms_resolve_an_alias_only_canonical(self):
        forms = present_surface_forms(["Communication"], "Worked cross-functional with stakeholders.")
        self.assertIn("cross-functional", forms)
        self.assertNotEqual(forms, ["Communication"])

    def test_absent_canonical_falls_back_to_its_label(self):
        self.assertEqual(present_surface_forms(["Communication"], "no related words here"), ["Communication"])

    def test_alias_only_keyword_is_not_reported_unparseable(self):
        profile = parse_profile_text(
            "## Experience\n\n"
            "### ML Intern - Acme\n"
            "- Worked cross-functional with stakeholders on Python models.\n"
        )
        match = MatchResult(
            score=0.9,
            band="strong",
            coverage=KeywordCoverage(matched=["Communication"], missing=[]),
            missing_keywords=[],
        )
        resume = GeneratedResume(pdf_path="/tmp/fake.pdf")
        with mock.patch(
            "jobpilot.pipeline.extract_pdf_text",
            return_value="Education Experience Projects Technical Skills cross-functional",
        ):
            _run_parseability(test_config(), resume, match, profile)
        self.assertTrue(resume.parseability_ok, resume.parseability_detail)


if __name__ == "__main__":
    unittest.main()
