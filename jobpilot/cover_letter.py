"""Short cover letter generated from the same master-profile material.

The letter is built from fixed, fact-free boilerplate plus verbatim profile
bullets. It is validated against the profile with an allowlist for the
boilerplate and for the target company/role words, so it cannot introduce a
number, employer or metric the profile does not state.
"""

from __future__ import annotations

from pathlib import Path

from jobpilot.config import Config
from jobpilot.facts import FactValidator, content_tokens
from jobpilot.models import GeneratedCoverLetter, JobPosting, MatchResult
from jobpilot.profile import Profile
from jobpilot.resume.generator import ResumeGenerator, latex_escape, latex_safe_text, slugify
from jobpilot.lexicon import extract_terms

BOILERPLATE_WORDS = frozenset(
    """
    dear hiring team i am writing apply position currently student and seeking
    an internship that runs january may or june my most relevant work would
    welcome opportunity contribute learn from your thank you for consideration
    sincerely
    """.split()
)

TEMPLATE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage{parskip}
\begin{document}
\begin{flushright}
@@NAME@@ \\
@@CONTACT@@
\end{flushright}

\vspace{0.5em}

Dear @@COMPANY@@ Hiring Team,

I am writing to apply for the @@TITLE@@ position. I am currently a student at
@@INSTITUTION@@, and I am seeking an internship that runs January to May or June.

My most relevant work: @@BULLETS@@

I would welcome the opportunity to contribute to @@COMPANY@@ and to learn from
your team. Thank you for your consideration.

Sincerely,\\
@@NAME@@ \\
@@CONTACT@@
\end{document}
"""


class CoverLetterGenerator:
    def __init__(self, profile: Profile, config: Config):
        self.profile = profile
        self.config = config
        self.validator = FactValidator(profile.raw_text, allowed_words=BOILERPLATE_WORDS)

    def generate(
        self,
        posting: JobPosting,
        match: MatchResult,
        out_dir: str,
        resume_generator: ResumeGenerator | None = None,
    ) -> GeneratedCoverLetter:
        jd_text = posting.searchable_text()
        jd_terms = set(extract_terms(jd_text))
        bullets = self._select_bullets(jd_terms)
        institution = ""
        if self.profile.education:
            inst = self.profile.education[0]
            institution = inst.org or inst.title
        contact = self._contact_line()

        values = {
            "@@NAME@@": self.profile.name,
            "@@CONTACT@@": contact,
            "@@COMPANY@@": posting.company or "your company",
            "@@TITLE@@": posting.title or "the role",
            "@@INSTITUTION@@": institution,
            "@@BULLETS@@": " ".join(bullets),
        }

        def render(escape, fallbacks: dict[str, str] | None = None) -> str:
            body = TEMPLATE
            for key, value in values.items():
                rendered = escape(value)
                if fallbacks and not rendered.strip():
                    rendered = fallbacks.get(key, rendered)
                body = body.replace(key, rendered)
            return body

        # Validate the faithful text first, then write a LaTeX-safe rendering.
        # pdflatex cannot typeset every script a posting may use; a non-ASCII
        # title/company would otherwise fail the compile (G3). Sanitising only
        # after validation keeps the fact check on the real words.
        body = render(latex_escape)
        violations = self._validate(body, posting)
        if violations:
            raise ValueError("cover letter violates the no-invention rule: " + "; ".join(violations[:5]))

        safe_body = render(latex_safe_text, {"@@COMPANY@@": "your company", "@@TITLE@@": "the role"})
        job_dir = Path(out_dir) / f"{posting.source}-{slugify(posting.company)}-{slugify(posting.title)}-{posting.job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        tex_path = job_dir / "cover_letter.tex"
        tex_path.write_text(safe_body, encoding="utf-8")
        text = "\n".join(bullets)
        return GeneratedCoverLetter(tex_path=str(tex_path), text=text)

    def _select_bullets(self, jd_terms: set[str], count: int = 2) -> list[str]:
        candidates: list[tuple[float, str]] = []
        for entry in [*self.profile.experiences, *self.profile.projects]:
            for bullet in entry.bullets:
                terms = set(extract_terms(bullet))
                rel = len(terms & jd_terms)
                candidates.append((rel, bullet))
        candidates.sort(key=lambda x: x[0], reverse=True)
        chosen = [b for _, b in candidates[:count]]
        if not chosen:
            chosen = self.profile.all_bullets[:count]
        return chosen

    def _contact_line(self) -> str:
        c = self.profile.contact
        bits = [c.get("email", ""), c.get("phone", ""), c.get("linkedin", ""), c.get("github", "")]
        return " | ".join(b for b in bits if b)

    def _validate(self, body: str, posting: JobPosting) -> list[str]:
        from jobpilot.facts import extract_numbers

        allowed = set(content_tokens(posting.company + " " + posting.title))
        allowed_numbers = extract_numbers(posting.searchable_text())
        return [
            str(v)
            for v in self.validator.validate(self._plain_text(body), extra_allowed=allowed, extra_numbers=allowed_numbers)
        ]

    @staticmethod
    def _plain_text(body: str) -> str:
        """Strip LaTeX scaffolding so only visible text is fact-checked."""
        import re as _re

        text = _re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", body)
        text = text.replace("\\", " ").replace("{", " ").replace("}", " ").replace("$", " ")
        return text
