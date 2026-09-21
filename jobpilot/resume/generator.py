"""Tailored resume generation from the master profile.

Tailoring means **selecting, reordering and re-emphasising real content**:

* entries, bullet order and skills order are chosen by relevance to the JD;
* existing measured values are bolded for emphasis;
* an outcome-first ("XYZ") rewrite may reorder an existing bullet's clauses,
  but only when the result still passes the strict fact validator.

Nothing is invented. The generator reuses the verbatim LaTeX preamble of the
style template, so the visual style is preserved exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from jobpilot.config import Config
from jobpilot.facts import FactValidator, bold_measurements, content_tokens
from jobpilot.lexicon import extract_terms, normalize
from jobpilot.models import GeneratedResume, JobPosting, MatchResult
from jobpilot.profile import Entry, Profile
from jobpilot.resume.xyz import rewrite_bullet

SECTION_EXPERIENCE = "Experience"
SECTION_PROJECTS = "Projects"
SECTION_SKILLS = "Technical Skills"
SECTION_EDUCATION = "Education"

_UNICODE_MAP = {
    "\u2013": "--",
    "\u2014": "---",
    "\u2018": "`",
    "\u2019": "'",
    "\u201c": "``",
    "\u201d": "''",
    "\u00d7": r"$\times$",
    "\u2265": r"$\geq$",
    "\u2264": r"$\leq$",
    "\u2026": r"\ldots{}",
    "\u00b7": r"$\cdot$",
    "\u2192": r"$\rightarrow$",
    "\u2212": "-",
    "\u00a0": " ",
}

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in _LATEX_SPECIALS:
            out.append(_LATEX_SPECIALS[ch])
        else:
            out.append(ch)
    escaped = "".join(out)
    for src, dst in _UNICODE_MAP.items():
        escaped = escaped.replace(src, dst)
    return escaped


@dataclass
class RenderedResume:
    body: str
    sections: list[str]
    content_text: str
    provenance: list[dict] = field(default_factory=list)


def slugify(text: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:max_length] or "job"


class ResumeGenerator:
    def __init__(self, profile: Profile, config: Config):
        self.profile = profile
        self.config = config
        self.validator = FactValidator(profile.raw_text)
        self.template_path = config.resolve(config.profile.style_template)

    # ------------------------------------------------------------------ public
    def generate(self, posting: JobPosting, match: MatchResult, out_dir: str) -> GeneratedResume:
        preamble = self._load_preamble()
        rendered = self.render(posting, match)

        violations = self.validate_content(rendered)
        if violations:
            raise ContentInvariantError(violations)

        tex = self._assemble(preamble, rendered.body)
        job_dir = Path(out_dir) / f"{posting.source}-{slugify(posting.company)}-{slugify(posting.title)}-{posting.job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        tex_path = job_dir / "resume.tex"
        tex_path.write_text(tex, encoding="utf-8")
        return GeneratedResume(
            tex_path=str(tex_path),
            text=rendered.content_text,
            provenance=rendered.provenance,
            sections=rendered.sections,
        )

    def validate_content(self, rendered: RenderedResume) -> list[str]:
        violations = []
        for item in rendered.provenance:
            bullet = item.get("raw", "")
            allowed = set(content_tokens(item.get("source", "")))
            for v in self.validator.validate(bullet, extra_allowed=allowed):
                violations.append(f"{v} in {item.get('ref', '?')}")
        return violations

    # ---------------------------------------------------------------- rendering
    def render(self, posting: JobPosting, match: MatchResult) -> RenderedResume:
        jd_text = posting.searchable_text()
        jd_terms = set(extract_terms(jd_text))
        jd_vocab = set(content_tokens(jd_text))

        sections: list[str] = []
        content_parts: list[str] = []
        provenance: list[dict] = []
        blocks: list[str] = []

        blocks.append(self._render_heading())
        sections.append(SECTION_EDUCATION)

        if self.profile.education:
            body, refs = self._render_education()
            blocks.append(body)
            provenance.extend(refs)

        experiences = self._select_experiences(jd_terms, jd_vocab)
        if experiences:
            body, refs = self._render_experiences(experiences, jd_terms, jd_vocab)
            blocks.append(body)
            provenance.extend(refs)
            sections.append(SECTION_EXPERIENCE)

        projects = self._select_projects(jd_terms, jd_vocab)
        if projects:
            body, refs = self._render_projects(projects, jd_terms, jd_vocab)
            blocks.append(body)
            provenance.extend(refs)
            sections.append(SECTION_PROJECTS)

        positions = self._select_positions(jd_terms, jd_vocab)
        if positions:
            body, refs = self._render_positions(positions, jd_terms, jd_vocab)
            blocks.append(body)
            provenance.extend(refs)

        if self.profile.skills:
            body = self._render_skills(jd_text)
            blocks.append(body)
            sections.append(SECTION_SKILLS)

        for item in provenance:
            content_parts.append(item.get("raw", ""))
        return RenderedResume(
            body="\n\n".join(blocks),
            sections=sections,
            content_text="\n".join(content_parts),
            provenance=provenance,
        )

    # --------------------------------------------------------------- selection
    @staticmethod
    def _relevance(text: str, jd_terms: set[str], jd_vocab: set[str]) -> float:
        terms = set(extract_terms(text))
        term_hits = len(terms & jd_terms)
        token_hits = sum(1 for w in content_tokens(text) if w in jd_vocab)
        return term_hits * 2.0 + min(token_hits, 25) * 0.1

    def _select_experiences(self, jd_terms: set[str], jd_vocab: set[str]) -> list[Entry]:
        include_non_ai = bool(self.config.apply.submission.get("include_non_ai", False)) or bool(
            getattr(self.config.match, "include_non_ai_experience", False)
        )
        scored = []
        for idx, entry in enumerate(self.profile.experiences):
            rel = self._relevance(entry.searchable_text(), jd_terms, jd_vocab)
            is_non_ai = "non_ai" in entry.tags
            if is_non_ai and not include_non_ai and rel <= 0:
                continue
            scored.append((rel, idx, entry))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [e for _, _, e in scored]

    def _select_projects(self, jd_terms: set[str], jd_vocab: set[str]) -> list[Entry]:
        max_projects = int(getattr(self.config.match, "max_projects", 4) or 4)
        scored = []
        for idx, entry in enumerate(self.profile.projects):
            rel = self._relevance(entry.searchable_text(), jd_terms, jd_vocab)
            scored.append((rel, idx, entry))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [e for _, _, e in scored[:max_projects]]

    def _select_positions(self, jd_terms: set[str], jd_vocab: set[str]) -> list[Entry]:
        if not getattr(self.config.match, "include_positions", False):
            return []
        return list(self.profile.positions)

    # --------------------------------------------------------------- rendering
    def _render_heading(self) -> str:
        c = self.profile.contact
        name = latex_escape(self.profile.name or "Candidate")
        parts: list[str] = []
        phone = c.get("phone")
        email = c.get("email")
        linkedin = c.get("linkedin")
        github = c.get("github")
        if phone:
            parts.append(rf"\raisebox{{-0.1\height}}\faPhone\ {latex_escape(phone)}")
        if email:
            parts.append(
                rf"\href{{mailto:{email}}}{{\raisebox{{-0.2\height}}\faEnvelope\  \underline{{{latex_escape(email)}}}}}"
            )
        if linkedin:
            url = linkedin if linkedin.startswith("http") else f"https://{linkedin}"
            parts.append(
                rf"\href{{{url}}}{{\raisebox{{-0.2\height}}\faLinkedin\ \underline{{{latex_escape(linkedin)}}}}}"
            )
        if github:
            url = github if github.startswith("http") else f"https://{github}"
            parts.append(
                rf"\href{{{url}}}{{\raisebox{{-0.2\height}}\faGithub\ \underline{{{latex_escape(github)}}}}}"
            )
        joined = " ~\n    ".join(parts)
        return (
            "\\begin{center}\n"
            f"    {{\\Huge \\scshape {name}}} \\\\ \\vspace{{1pt}}\n"
            f"    \\small {joined}\n"
            "    \\vspace{-8pt}\n"
            "\\end{center}\n"
        )

    def _render_education(self) -> tuple[str, list[dict]]:
        lines = ["\\section{Education}", "  \\resumeSubHeadingListStart"]
        for entry in self.profile.education:
            title = latex_escape(entry.org or entry.title)
            dates = latex_escape(entry.dates or "")
            degree = latex_escape(entry.tagline or entry.title)
            location = latex_escape(entry.location or "")
            lines.append("    \\resumeSubheading")
            lines.append(f"      {{{title}}}{{{dates}}}")
            lines.append(f"      {{{degree}}}{{{location}}}")
        lines.append("  \\resumeSubHeadingListEnd")
        return "\n".join(lines), []

    def _render_experiences(self, entries: list[Entry], jd_terms: set[str], jd_vocab: set[str]) -> tuple[str, list[dict]]:
        lines = ["\\section{Experience}", "  \\resumeSubHeadingListStart"]
        refs: list[dict] = []
        for entry in entries:
            lines.append("    \\resumeSubheading")
            lines.append(f"      {{{latex_escape(entry.title)}}}{{{latex_escape(entry.dates)}}}")
            lines.append(f"      {{{latex_escape(entry.org)}}}{{{latex_escape(entry.location)}}}")
            lines.append("      \\resumeItemListStart")
            for ref in self._bullet_refs(entry, "experience", jd_terms, jd_vocab):
                lines.append(f"        \\resumeItem{{{ref['latex']}}}")
                refs.append(ref)
            lines.append("      \\resumeItemListEnd")
        lines.append("  \\resumeSubHeadingListEnd")
        return "\n".join(lines), refs

    def _render_projects(self, entries: list[Entry], jd_terms: set[str], jd_vocab: set[str]) -> tuple[str, list[dict]]:
        lines = ["\\section{" + SECTION_PROJECTS + "}", "    \\vspace{-5pt}", "    \\resumeSubHeadingListStart"]
        refs: list[dict] = []
        for entry in entries:
            url = ""
            for link in entry.links:
                m = re.search(r"(https?://\S+|github\.com/\S+)", link)
                if m:
                    url = m.group(1)
                    break
            if url and not url.startswith("http"):
                url = f"https://{url}"
            name = latex_escape(entry.title)
            if url:
                name = rf"\textbf{{\href{{{url}}}{{{name}}}}}"
            else:
                name = rf"\textbf{{{name}}}"
            stack = latex_escape(self._clean_stack(entry.stack))
            heading = f"{name} $|$ \\emph{{{stack}}}" if stack else name
            year = latex_escape(entry.year or "")
            lines.append("      \\resumeProjectHeading")
            lines.append(f"          {{{heading}}}{{{year}}}")
            lines.append("          \\resumeItemListStart")
            for ref in self._bullet_refs(entry, "project", jd_terms, jd_vocab):
                lines.append(f"            \\resumeItem{{{ref['latex']}}}")
                refs.append(ref)
            lines.append("          \\resumeItemListEnd")
            lines.append("          \\vspace{-11pt}")
        lines.append("    \\resumeSubHeadingListEnd")
        lines.append("\\vspace{-15pt}")
        return "\n".join(lines), refs

    def _render_positions(self, entries: list[Entry], jd_terms: set[str], jd_vocab: set[str]) -> tuple[str, list[dict]]:
        lines = ["\\section{Positions of Responsibility}", "  \\resumeSubHeadingListStart"]
        refs: list[dict] = []
        for entry in entries:
            lines.append("    \\resumeSubheading")
            lines.append(f"      {{{latex_escape(entry.title)}}}{{{latex_escape(entry.dates)}}}")
            lines.append(f"      {{{latex_escape(entry.org)}}}{{{latex_escape(entry.location)}}}")
            lines.append("      \\resumeItemListStart")
            for ref in self._bullet_refs(entry, "position", jd_terms, jd_vocab):
                lines.append(f"        \\resumeItem{{{ref['latex']}}}")
                refs.append(ref)
            lines.append("      \\resumeItemListEnd")
        lines.append("  \\resumeSubHeadingListEnd")
        return "\n".join(lines), refs

    def _render_skills(self, jd_text: str) -> str:
        jd_terms = set(extract_terms(jd_text))
        jd_norm = normalize(jd_text)
        categories = list(self.profile.skills.items())

        def cat_relevance(item: tuple[str, list[str]]) -> float:
            name, items = item
            score = len(set(extract_terms(name)) & jd_terms) * 2
            for skill in items:
                if normalize(skill) in jd_norm or any(t.lower() in jd_norm for t in extract_terms(skill)):
                    score += 1
            return score

        categories.sort(key=cat_relevance, reverse=True)

        lines = ["\\section{" + SECTION_SKILLS + "}", " \\begin{itemize}[leftmargin=0.15in, label={}]", "    \\small{\\item{"]
        rendered_categories = []
        for name, items in categories:
            ordered = sorted(items, key=lambda s: 0 if _skill_in_jd(s, jd_text, jd_terms) else 1)
            rendered_categories.append(
                rf"     \textbf{{{latex_escape(name)}}}{{: {', '.join(latex_escape(s) for s in ordered)}}}"
            )
        lines.append(" \\\\\n".join(rendered_categories))
        lines.append("    }}")
        lines.append(" \\end{itemize}")
        lines.append(" \\vspace{-16pt}")
        return "\n".join(lines)

    def _bullet_refs(self, entry: Entry, kind: str, jd_terms: set[str], jd_vocab: set[str]) -> list[dict]:
        scored = []
        for idx, bullet in enumerate(entry.bullets):
            rel = self._relevance(bullet, jd_terms, jd_vocab)
            scored.append((rel, idx, bullet))
        scored.sort(key=lambda x: (-x[0], x[1]))
        bold_metrics = bool(getattr(self.config.match, "bold_metrics", True))
        refs = []
        for _, idx, bullet in scored:
            rewritten = rewrite_bullet(bullet, self.validator)
            latex = latex_escape(rewritten)
            if bold_metrics:
                latex = bold_measurements(latex)
            refs.append(
                {
                    "ref": f"{kind}:{entry.title}:{idx}",
                    "source": entry.searchable_text(),
                    "raw": rewritten,
                    "original": bullet,
                    "latex": latex,
                }
            )
        return refs

    def _clean_stack(self, stack: str) -> str:
        return re.sub(r"\s+", " ", stack or "").strip()

    def _load_preamble(self) -> str:
        text = Path(self.template_path).read_text(encoding="utf-8")
        marker = "\\begin{document}"
        if marker in text:
            return text[: text.index(marker) + len(marker)]
        return text

    @staticmethod
    def _assemble(preamble: str, body: str) -> str:
        return f"{preamble}\n\n{body}\n\n\\end{{document}}\n"


def _skill_in_jd(skill: str, jd_text: str, jd_terms: set[str]) -> bool:
    return bool(set(extract_terms(skill)) & jd_terms) or normalize(skill) in normalize(jd_text)


class ContentInvariantError(RuntimeError):
    """Raised when generated content contains a fact absent from the profile."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("generated content violates the no-invention rule: " + "; ".join(violations[:5]))
