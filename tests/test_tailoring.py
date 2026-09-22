import os
import tempfile
import unittest
from pathlib import Path

from jobpilot.matching import Matcher
from jobpilot.profile import load_profile
from jobpilot.resume.compiler import compile_tex
from jobpilot.resume.generator import ResumeGenerator
from jobpilot.resume.parseability import check_parseability, extract_pdf_text
from tests.helpers import posting, test_config

REAL_PROFILE = "/mnt/d/LaTeX/resume/PROFILE.md"
REAL_STYLE = "/mnt/d/LaTeX/resume/Abhigyan_Resume_AI_ML.tex"
REAL_ENGINE = "/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdflatex.exe"
REAL_PDFTOTEXT = "/mnt/d/LaTeX/MiKTeX/miktex/bin/x64/pdftotext.exe"

_HAS_TOOLCHAIN = all(os.path.exists(p) for p in (REAL_PROFILE, REAL_STYLE, REAL_ENGINE, REAL_PDFTOTEXT))


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


if __name__ == "__main__":
    unittest.main()
