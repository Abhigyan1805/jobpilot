"""The ``jobpilot present`` review surface.

Turns the queued matches into a single self-contained HTML page the captain can
browse and choose from - one card per match, ordered by score, each with the
tailored resume and cover letter viewable beside the direct apply link.

Selection is deliberately conservative and is *presentation only*: it filters
and orders what the pipeline already produced. It never re-scores, never invents
resume content and never submits anything.

Fit comes from the data the pipeline already computes: a posting's role
relevance across the configured technical domains, confirmed by the matched
skills against the master profile. Non-technical roles are excluded outright -
not shown in a separate tier - and the role set is configurable through
``[present]`` rather than hardcoded. When nothing clears the floor, the closest
technical matches are shown with a note explaining why they are borderline,
instead of padding the list.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jobpilot.config import Config
from jobpilot.linkout import is_manual_source
from jobpilot.matching import Matcher
from jobpilot.models import JobPosting
from jobpilot.profile import load_profile
from jobpilot.review import safe_filename
from jobpilot.store import TRANSIENT_REVIEW_REASONS, Store


@dataclass
class ReviewCandidate:
    """A queued review item joined with its stored posting and score metadata."""

    review_id: int
    posting: JobPosting
    score: float
    band: str
    matched: list[str]
    gaps: list[str]
    reasons: list[str]
    resume_pdf: str = ""
    cover_pdf: str = ""
    packet_dir: str = ""
    window_label: str = ""
    window_confidence: float = 0.0
    review_category: str = ""
    review_reason: str = ""
    page_count: int = 0
    page_limit: int = 0

    @property
    def company(self) -> str:
        return self.posting.company

    @property
    def title(self) -> str:
        return self.posting.title

    @property
    def location(self) -> str:
        return self.posting.location

    @property
    def apply_url(self) -> str:
        return self.posting.apply_url or self.posting.url


@dataclass
class PresentMatch:
    """A selected candidate plus its computed fit and safety classification."""

    candidate: ReviewCandidate
    role_relevance: float
    domain_scores: dict[str, float]
    technical_relevance: float
    best_domain: str = ""
    core_skill_hit: bool = False
    borderline: bool = False
    borderline_note: str = ""
    route: str = "review"
    route_label: str = "Review-only"
    safety_detail: str = ""


@dataclass
class ExcludedCandidate:
    candidate: ReviewCandidate
    reason: str


@dataclass
class SelectionResult:
    included: list[PresentMatch] = field(default_factory=list)
    borderline: list[PresentMatch] = field(default_factory=list)
    excluded: list[ExcludedCandidate] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.included) + len(self.borderline)


def _posting_from_row(row) -> JobPosting:
    return JobPosting(
        source=row["source"],
        job_id=row["job_id"],
        company=row["company"] or "",
        title=row["title"] or "",
        url=row["url"] or "",
        apply_url=row["apply_url"] or "",
        apply_email=row["apply_email"] or "",
        location=row["location"] or "",
        description=row["description"] or "",
        employment_type=row["employment_type"] or "",
        published_at=row["published_at"] or "",
        is_remote=None if row["is_remote"] is None else bool(row["is_remote"]),
    )


def _parse_json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def build_candidates(store: Store) -> list[ReviewCandidate]:
    """Join pending review rows with their stored postings."""
    postings = {row["stable_id"]: row for row in store.list_postings()}
    candidates: list[ReviewCandidate] = []
    for row in store.list_review("pending"):
        posting_row = postings.get(row["stable_id"])
        if posting_row is None:
            continue
        route_row = store.latest_review_application(row["stable_id"])
        candidates.append(
            ReviewCandidate(
                review_id=int(row["id"]),
                posting=_posting_from_row(posting_row),
                score=float(row["score"] or 0.0),
                band=posting_row["band"] or "",
                matched=_parse_json_list(row["matched_keywords"]),
                gaps=_parse_json_list(row["gaps"]),
                reasons=_parse_json_list(row["reasons"]),
                resume_pdf=row["resume_pdf"] or "",
                cover_pdf=row["cover_pdf"] or "",
                packet_dir=row["packet_dir"] or "",
                window_label=posting_row["window_label"] or "",
                window_confidence=float(posting_row["window_confidence"] or 0.0),
                review_category=(route_row["review_category"] or "") if route_row else "",
                review_reason=(route_row["review_reason"] or "") if route_row else "",
                page_count=int(row["resume_pages"] or 0),
                page_limit=int(row["resume_page_limit"] or 0),
            )
        )
    return candidates


@lru_cache(maxsize=1024)
def _exclude_re(term: str) -> re.Pattern[str]:
    # Every exclusion is a whole-word phrase. Prefix matching would drop genuine
    # technical roles ("visual" -> "Data Visualization", "operations" ->
    # "Machine Learning Operations"), so the list spells out the non-technical
    # phrases instead.
    escaped = re.escape(term.lower().strip())
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def title_is_excluded(title: str, exclude_terms: list[str]) -> str:
    """Return the first non-technical role term the title matches, else ""."""
    normalized = (title or "").lower()
    for term in exclude_terms:
        if term and _exclude_re(term).search(normalized):
            return term
    return ""


def _technical_relevance(
    domain_scores: dict[str, float], matched: list[str], config: Config
) -> tuple[float, str, bool]:
    present = config.present
    core = set(present.core_skills)
    core_skill_hit = any(skill in core for skill in matched)
    best = 0.0
    best_domain = ""
    for domain in present.technical_domains:
        score = float(domain_scores.get(domain, 0.0))
        if domain in present.guarded_domains and not core_skill_hit:
            # A broad domain (research) only counts as technical when the
            # posting also asks for a core technical skill the profile supports.
            score = 0.0
        if score > best:
            best = score
            best_domain = domain
    return best, best_domain, core_skill_hit


def _classify_route(candidate: ReviewCandidate, config: Config) -> tuple[str, str, str]:
    """Return (route, label, detail) for the per-card safety state."""
    source = candidate.posting.source
    if source == "linkedin":
        return (
            "linkedin",
            "Review-only (LinkedIn)",
            "Not submitted. LinkedIn is discovered, tailored and packaged, never auto-submitted.",
        )
    if is_manual_source(config, source):
        return (
            "linkout",
            "Review-only link-out",
            "Not submitted. Manual link-out source: the pipeline prepares the packet and you submit.",
        )
    armed = bool(config.apply.enabled and config.apply.auto_apply_strong)
    if candidate.band == "strong":
        if armed and candidate.review_category in TRANSIENT_REVIEW_REASONS:
            return (
                "auto",
                "Auto-apply eligible",
                "Not submitted. Strong auto-apply band, queued only for a transient reason "
                "(daily cap, missing channel or auto-apply config); auto-apply is enabled, "
                "so a later run can submit it once that condition clears.",
            )
        if not armed:
            return (
                "review",
                "Review-only (auto-apply off)",
                "Not submitted. Strong auto-apply band, but auto-apply is off in config, so it was queued for review.",
            )
        reason = candidate.review_reason or candidate.review_category or "the pipeline's guardrails"
        return (
            "review",
            "Review-only",
            f"Not submitted. Strong auto-apply band, but the pipeline routed it to review: {reason}.",
        )
    band = candidate.band or "unknown"
    return (
        "review",
        "Review-only",
        f"Not submitted. Band '{band}' is review-only; you submit from the direct link.",
    )


def select_matches(
    candidates: list[ReviewCandidate], matcher: Matcher, config: Config
) -> SelectionResult:
    """Select the genuine technical matches; exclude everything else.

    A posting is included when its role relevance in a configured technical
    domain reaches ``present.min_role_relevance`` and its title is not a
    non-technical role. Candidates between ``borderline_role_relevance`` and the
    floor are held as borderline and shown only when nothing clears the floor.
    """
    present = config.present
    result = SelectionResult()
    borderline: list[PresentMatch] = []

    for candidate in candidates:
        excluded_term = title_is_excluded(candidate.title, present.exclude_terms)
        domain_scores = matcher.role_relevance_by_domain(candidate.posting)
        technical, best_domain, core_hit = _technical_relevance(
            domain_scores, candidate.matched, config
        )
        route, label, detail = _classify_route(candidate, config)

        if excluded_term:
            result.excluded.append(
                ExcludedCandidate(candidate, f"non-technical role term '{excluded_term}'")
            )
            continue

        match = PresentMatch(
            candidate=candidate,
            role_relevance=max(domain_scores.values(), default=0.0),
            domain_scores=domain_scores,
            technical_relevance=technical,
            best_domain=best_domain,
            core_skill_hit=core_hit,
            route=route,
            route_label=label,
            safety_detail=detail,
        )

        if technical >= present.min_role_relevance:
            result.included.append(match)
        elif technical >= present.borderline_role_relevance:
            match.borderline = True
            match.borderline_note = (
                f"role relevance {technical:.2f} in {best_domain or 'no technical domain'} is below "
                f"the {present.min_role_relevance:.2f} technical floor"
            )
            borderline.append(match)
        else:
            result.excluded.append(
                ExcludedCandidate(
                    candidate,
                    f"role relevance {technical:.2f} is below the technical floor",
                )
            )

    result.included.sort(key=lambda m: m.candidate.score, reverse=True)
    borderline.sort(key=lambda m: m.candidate.score, reverse=True)
    # Borderline is a fallback, never padding: show it only when nothing qualified.
    if not result.included:
        result.borderline = borderline[: present.max_borderline]
    return result


# --------------------------------------------------------------------- render

_CSS = """
:root {
  --bg: #f5f6f8; --card: #ffffff; --ink: #1a1d23; --muted: #5c6472;
  --line: #e3e6eb; --accent: #2f5bea; --good: #10784a; --good-bg: #e7f5ee;
  --warn: #9a5b00; --warn-bg: #fdf1de; --bad: #b42318; --bad-bg: #fdeceb;
  --chip: #eef1f6;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  padding: 32px 20px 64px;
}
.wrap { max-width: 1080px; margin: 0 auto; min-width: 0; }
header.page { margin-bottom: 20px; }
h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: -0.02em; }
.sub { color: var(--muted); margin: 0; }
.stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.stat {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 14px; min-width: 0;
}
.stat b { display: block; font-size: 20px; }
.stat span { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.safety {
  display: flex; gap: 10px; align-items: flex-start; background: var(--good-bg);
  border: 1px solid #bfe3cf; color: #0c5734; border-radius: 10px; padding: 12px 14px;
  margin: 0 0 22px; font-size: 14px;
}
.safety strong { color: #0c5734; }
.section-title { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 28px 0 12px; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 18px 20px; margin-bottom: 18px; min-width: 0;
  box-shadow: 0 1px 2px rgba(20, 24, 33, 0.04);
}
.card.borderline { border-style: dashed; }
.card-head { display: flex; gap: 14px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.rank { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 13px; padding-top: 4px; }
.role { flex: 1 1 320px; min-width: 0; }
.role h2 { font-size: 18px; margin: 0; overflow-wrap: anywhere; }
.role .company { color: var(--accent); font-weight: 600; }
.role .title { color: var(--ink); }
.role h2 a.title-link {
  color: var(--ink); text-decoration: underline; text-decoration-thickness: 2px;
  text-decoration-color: var(--accent); text-underline-offset: 3px;
}
.role h2 a.title-link:hover { color: var(--accent); }
.score {
  text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap;
}
.score .num { font-size: 22px; font-weight: 700; }
.score .band { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 0; }
.chip {
  background: var(--chip); border-radius: 999px; padding: 3px 10px; font-size: 12px; color: var(--muted);
  max-width: 100%; overflow-wrap: anywhere;
}
.pagebadge { display: inline-block; border-radius: 999px; padding: 3px 11px; font-size: 12px; margin-top: 10px; }
.pagebadge.ok { background: var(--good-bg); color: var(--good); }
.pagebadge.warn { background: var(--bad-bg); color: var(--bad); font-weight: 700; }
.meta { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 12px 0 0; color: var(--muted); font-size: 13px; }
.meta span { overflow-wrap: anywhere; }
.meta b { color: var(--ink); font-weight: 600; }
.skills { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 14px; margin-top: 14px; min-width: 0; }
.skills h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 8px; color: var(--muted); }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { border-radius: 6px; padding: 3px 9px; font-size: 12px; overflow-wrap: anywhere; }
.tag.matched { background: var(--good-bg); color: var(--good); }
.tag.gap { background: var(--warn-bg); color: var(--warn); }
.tag.none { background: var(--chip); color: var(--muted); }
.route { display: flex; gap: 10px; align-items: flex-start; margin-top: 16px; padding: 10px 12px; border-radius: 10px; font-size: 13px; }
.route.auto { background: var(--good-bg); color: #0c5734; }
.route.linkout, .route.linkedin { background: var(--warn-bg); color: var(--warn); }
.route.review { background: var(--chip); color: var(--muted); }
.route .badge { font-weight: 700; white-space: nowrap; }
.note { background: var(--warn-bg); color: var(--warn); border-radius: 8px; padding: 8px 11px; font-size: 13px; margin-top: 12px; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 16px; min-width: 0; }
.apply-url { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; min-width: 0; }
.btn {
  display: inline-block; text-decoration: none; border-radius: 8px; padding: 8px 14px;
  font-size: 14px; font-weight: 600; border: 1px solid var(--accent); color: #fff; background: var(--accent);
  overflow-wrap: anywhere;
}
.btn.apply { background: var(--ink); border-color: var(--ink); }
.pdfs { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); gap: 14px; margin-top: 16px; min-width: 0; }
.pdf { min-width: 0; }
.pdf h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 0 0 8px; }
.pdf iframe {
  width: 100%; height: 420px; border: 1px solid var(--line); border-radius: 8px; background: #fff;
}
.pdf .missing { color: var(--bad); font-size: 13px; }
.empty { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 22px; }
footer { color: var(--muted); font-size: 12px; margin-top: 32px; }
a { color: var(--accent); }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _pretty_window(label: str) -> str:
    """Render a window label readably (the rubric emits "Jan-5" for May)."""
    if not label or label == "unknown":
        return label or "unknown"

    def month_name(token: str) -> str:
        if token.isdigit() and 1 <= int(token) <= 12:
            return _MONTH_ABBR[int(token)]
        return token

    return re.sub(r"[A-Za-z0-9]+", lambda m: month_name(m.group(0)), label)


def _window_evidence(candidate: ReviewCandidate) -> str:
    label = _pretty_window(candidate.window_label)
    if candidate.window_confidence:
        return f"{label} (confidence {candidate.window_confidence:.2f})"
    return label


def _page_badge(candidate: ReviewCandidate) -> str:
    """A visible page-count badge, warning when the resume is over the limit."""
    if candidate.page_count <= 0 or candidate.page_limit <= 0:
        return ""
    if candidate.page_count <= candidate.page_limit:
        label = "1-page" if candidate.page_count == 1 else f"{candidate.page_count}-page"
        return f'<span class="pagebadge ok">Resume: {label} \u2713</span>'
    return (
        f'<span class="pagebadge warn">Resume is {candidate.page_count} pages, '
        f"limit is {candidate.page_limit} \u2014 needs attention</span>"
    )


def _tags(values: list[str], kind: str) -> str:
    if not values:
        return '<span class="tag none">none</span>'
    return "".join(f'<span class="tag {kind}">{_esc(v)}</span>' for v in values)


def _asset_slug(candidate: ReviewCandidate) -> str:
    base = safe_filename(
        f"{candidate.posting.source}-{candidate.company}-{candidate.title}", max_length=48
    )
    digest = hashlib.sha1(candidate.posting.stable_id.encode("utf-8")).hexdigest()[:10]
    return f"{base}-{digest}"


def _copy_asset(src: str, dest: Path) -> str:
    if not src or not Path(src).exists():
        return ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest.name


def _render_card(
    match: PresentMatch, rank: int, assets_rel: str, slug: str, resume_name: str, cover_name: str
) -> str:
    c = match.candidate
    css = "card borderline" if match.borderline else "card"
    domains = ", ".join(f"{name}={score:.2f}" for name, score in match.domain_scores.items())
    resume_rel = f"{assets_rel}/{slug}/resume.pdf" if resume_name else ""
    cover_rel = f"{assets_rel}/{slug}/cover_letter.pdf" if cover_name else ""
    note = ""
    if match.borderline and match.borderline_note:
        note = f'<div class="note">Borderline: {_esc(match.borderline_note)}.</div>'

    # The tailored resume is the card's primary affordance: the job title opens
    # it, and so does the first action button. The posting link stays a separate,
    # clearly-labelled button so "read the resume I generated" and "go to the
    # posting" cannot be confused. Both are plain relative anchors, so they work
    # when index.html is opened straight from disk (no server, no JavaScript).
    if resume_rel:
        title_html = (
            f'<a class="title-link" href="{_esc(resume_rel)}" target="_blank" rel="noopener" '
            f'title="Open the tailored resume PDF">{_esc(c.title)}</a>'
        )
    else:
        title_html = _esc(c.title)

    resume_action = ""
    if resume_rel:
        resume_action = (
            f'<a class="btn resume" href="{_esc(resume_rel)}" target="_blank" rel="noopener">'
            f"Open tailored resume PDF \u2197</a>"
        )

    pdfs = []
    if resume_name:
        pdfs.append(_pdf_block("Tailored resume", resume_rel))
    else:
        pdfs.append('<div class="pdf"><h3>Tailored resume</h3><p class="missing">No resume PDF was produced.</p></div>')
    if cover_name:
        pdfs.append(_pdf_block("Cover letter", cover_rel))
    else:
        pdfs.append('<div class="pdf"><h3>Cover letter</h3><p class="missing">No cover letter PDF was produced.</p></div>')

    return f"""
    <article class="{css}">
      <div class="card-head">
        <div class="rank">#{rank}</div>
        <div class="role">
          <h2><span class="company">{_esc(c.company)}</span> <span class="title">— {title_html}</span></h2>
        </div>
        <div class="score">
          <span class="num">{c.score:.3f}</span>
          <span class="band">{_esc(c.band or "unbanded")}</span>
        </div>
      </div>
      <div class="meta">
        <span><b>Location:</b> {_esc(c.location or "unspecified")}</span>
        <span><b>Window:</b> {_esc(_window_evidence(c))}</span>
        <span><b>Source:</b> {_esc(c.posting.source)}</span>
        <span><b>Technical relevance:</b> {match.technical_relevance:.2f}{_esc(f" ({match.best_domain})" if match.best_domain else "")}</span>
      </div>
      <div class="chips"><span class="chip">{_esc(domains or "no target domains")}</span></div>
      {_page_badge(c)}
      <div class="skills">
        <div>
          <h3>Matched skills (in the master profile)</h3>
          <div class="tags">{_tags(c.matched, "matched")}</div>
        </div>
        <div>
          <h3>Gaps (not in the profile; never inserted)</h3>
          <div class="tags">{_tags(c.gaps, "gap")}</div>
        </div>
      </div>
      {note}
      <div class="route {match.route}">
        <span class="badge">Not submitted</span>
        <span><b>{_esc(match.route_label)}</b> — {_esc(match.safety_detail)}</span>
      </div>
      <div class="actions">
        {resume_action}
        <a class="btn apply" href="{_esc(c.apply_url)}" target="_blank" rel="noopener">Apply / view posting ↗</a>
        <span class="apply-url">{_esc(c.apply_url)}</span>
      </div>
      <div class="pdfs">{"".join(pdfs)}</div>
    </article>
    """


def _pdf_block(label: str, rel: str) -> str:
    return (
        f'<div class="pdf"><h3>{_esc(label)}</h3>'
        f'<iframe src="{_esc(rel)}#view=FitH" title="{_esc(label)} PDF" loading="lazy"></iframe>'
        f'<p><a href="{_esc(rel)}" target="_blank" rel="noopener">Open {_esc(label)} PDF ↗</a></p></div>'
    )


def _render_document(selection: SelectionResult, config: Config, cards: list[str], generated_at: str) -> str:
    matched = len(selection.included)
    borderline = len(selection.borderline)
    if not cards:
        body = (
            '<div class="empty"><h2>No technical matches to show</h2>'
            "<p>Nothing in the review queue cleared the technical role-relevance floor "
            "for the configured target domains, and no borderline technical matches were "
            "close enough to show. The queue is not empty by mistake - these roles simply "
            "did not fit an AI/ML or technical profile.</p>"
            f"<p>{_esc(len(selection.excluded))} queued postings were excluded as "
            "non-technical or below the floor.</p></div>"
        )
    else:
        heading = ""
        if not selection.included and selection.borderline:
            heading = (
                '<div class="note" style="margin-bottom:16px">Nothing cleared the '
                f"{config.present.min_role_relevance:.2f} technical floor. The closest "
                "technical matches are shown below, each with a note explaining why it is "
                "borderline.</div>"
            )
        section = (
            '<div class="section-title">Closest technical matches (borderline)</div>'
            if not selection.included
            else ""
        )
        body = heading + section + "".join(cards)

    domains = ", ".join(config.present.technical_domains)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>jobpilot — internship matches for review</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="page">
    <h1>Internship matches for review</h1>
    <p class="sub">AI/ML and technical roles that fit the master profile, ordered by match score.
    Generated {_esc(generated_at)}.</p>
  </header>
  <div class="stats">
    <div class="stat"><b>{matched}</b><span>matches</span></div>
    <div class="stat"><b>{borderline}</b><span>borderline</span></div>
    <div class="stat"><b>{len(selection.excluded)}</b><span>excluded</span></div>
    <div class="stat"><b>0</b><span>submitted</span></div>
  </div>
  <div class="safety"><strong>Nothing was submitted.</strong>
    <span>This is a read-only review surface built from a dry run. It never applies to
    anything; you submit from the direct link when you choose. Technical domains in use:
    {_esc(domains)}.</span></div>
  {body}
  <footer>jobpilot present — selection reads the pipeline's own role relevance and matched
  skills; it never re-scores, invents resume content or submits.</footer>
</div>
</body>
</html>
"""


def resolve_out_dir(config: Config, override: str = "") -> Path:
    """Resolve the page directory: ``--out`` wins, else ``[present].out_dir``.

    ``[present].out_dir`` is resolved relative to ``[output].dir`` so the page
    lands beside the run's other artifacts by default.
    """
    if override:
        path = Path(override)
        return path if path.is_absolute() else Path(config.resolve(override))
    configured = Path(config.present.out_dir)
    if configured.is_absolute():
        return configured
    return Path(config.resolve(config.output.dir)) / configured


def run_present(
    config: Config,
    *,
    out_dir_override: str = "",
    generated_at: str | None = None,
) -> tuple[Path, SelectionResult]:
    """Select from the queued matches and render the review page."""
    store = Store(config.resolve(config.output.database))
    try:
        profile = load_profile(config.resolve(config.profile.path))
        matcher = Matcher(profile, config)
        candidates = build_candidates(store)
        selection = select_matches(candidates, matcher, config)
        index = render_page(
            selection, config, resolve_out_dir(config, out_dir_override), generated_at=generated_at
        )
        return index, selection
    finally:
        store.close()


def render_page(
    selection: SelectionResult,
    config: Config,
    out_dir: str | Path,
    *,
    generated_at: str | None = None,
) -> Path:
    """Write ``index.html`` (and copy the PDFs beside it); return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cards: list[str] = []
    rank = 0
    for match in [*selection.included, *selection.borderline]:
        rank += 1
        slug = _asset_slug(match.candidate)
        resume_name = _copy_asset(match.candidate.resume_pdf, out / "assets" / slug / "resume.pdf")
        cover_name = _copy_asset(match.candidate.cover_pdf, out / "assets" / slug / "cover_letter.pdf")
        cards.append(_render_card(match, rank, "assets", slug, resume_name, cover_name))
    index = out / "index.html"
    index.write_text(_render_document(selection, config, cards, generated_at), encoding="utf-8")
    return index
