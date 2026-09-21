"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobPosting:
    """A single posting normalised to one shape across every source."""

    source: str
    job_id: str
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    employment_type: str = ""
    published_at: str = ""
    apply_url: str = ""
    apply_email: str = ""
    is_remote: bool | None = None
    salary: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def stable_id(self) -> str:
        return f"{self.source}:{self.job_id}"

    def searchable_text(self) -> str:
        return " ".join(
            p for p in [self.title, self.company, self.location, self.employment_type, self.description] if p
        )


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    score: float = 0.0
    review_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail, "score": self.score}


@dataclass
class FilterResult:
    eligible: bool
    checks: list[CheckResult] = field(default_factory=list)
    window_label: str = ""
    window_confidence: float = 0.0
    reject_reasons: list[str] = field(default_factory=list)

    def reject_text(self) -> str:
        return "; ".join(self.reject_reasons)


@dataclass
class KeywordCoverage:
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        total = len(self.matched) + len(self.missing)
        return (len(self.matched) / total) if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"matched": self.matched, "missing": self.missing, "ratio": round(self.ratio, 4)}


@dataclass
class MatchResult:
    score: float
    reasons: list[str] = field(default_factory=list)
    rubric: dict[str, Any] = field(default_factory=dict)
    coverage: KeywordCoverage = field(default_factory=KeywordCoverage)
    missing_keywords: list[str] = field(default_factory=list)
    band: str = "reject"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "band": self.band,
            "reasons": self.reasons,
            "rubric": self.rubric,
            "coverage": self.coverage.to_dict(),
            "missing_keywords": self.missing_keywords,
        }


@dataclass
class GeneratedResume:
    tex_path: str = ""
    pdf_path: str = ""
    text: str = ""
    provenance: list[dict[str, Any]] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    parseability_ok: bool = False
    parseability_detail: str = ""
    compile_log: str = ""


@dataclass
class GeneratedCoverLetter:
    tex_path: str = ""
    pdf_path: str = ""
    text: str = ""


@dataclass
class SubmissionResult:
    status: str
    detail: str = ""
    adapter: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApplicationPlan:
    """Everything needed to decide and (optionally) submit one application."""

    posting: JobPosting
    match: MatchResult
    resume: GeneratedResume | None = None
    cover: GeneratedCoverLetter | None = None
    gaps: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    requires_review: bool = False
    review_reason: str = ""
