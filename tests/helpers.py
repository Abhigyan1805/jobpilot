"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

from jobpilot.answers import AnswerBook
from jobpilot.applying.base import SubmissionAdapter
from jobpilot.config import Config, default_config
from jobpilot.models import (
    ApplicationPlan,
    JobPosting,
    KeywordCoverage,
    MatchResult,
    SubmissionResult,
)
from jobpilot.profile import load_profile

FIXTURES = Path(__file__).parent / "fixtures"
MINI_PROFILE = FIXTURES / "mini_profile.md"
MINI_STYLE = FIXTURES / "mini_style.tex"


def test_config(
    tmp_path: Path | None = None,
    apply: dict | None = None,
    match: dict | None = None,
    filt: dict | None = None,
) -> Config:
    cfg = default_config()
    cfg.profile.path = str(MINI_PROFILE)
    cfg.profile.style_template = str(MINI_STYLE)
    cfg.profile.pdflatex = "pdflatex"
    cfg.profile.pdftotext = "pdftotext"
    cfg.output.dir = str((tmp_path / "out") if tmp_path else Path("out_test"))
    cfg.output.database = str((tmp_path / "jobpilot.db") if tmp_path else ":memory:")
    cfg.base_dir = str(FIXTURES)
    for section, values in (("apply", apply), ("match", match), ("filter", filt)):
        if not values:
            continue
        target = getattr(cfg, section)
        for key, value in values.items():
            if hasattr(target, key):
                setattr(target, key, value)
    return cfg


def mini_profile():
    return load_profile(MINI_PROFILE)


def empty_answers(profile=None) -> AnswerBook:
    return AnswerBook(answers={}, profile=profile or mini_profile())


def posting(
    *,
    source: str = "greenhouse",
    job_id: str = "1",
    company: str = "Acme",
    title: str = "Machine Learning Intern",
    location: str = "Bengaluru, India",
    description: str = "",
    employment_type: str = "Internship",
    is_remote: bool | None = None,
    apply_url: str | None = None,
    apply_email: str = "",
) -> JobPosting:
    return JobPosting(
        source=source,
        job_id=job_id,
        company=company,
        title=title,
        url=f"https://example.com/{source}/{job_id}",
        apply_url=apply_url if apply_url is not None else f"https://example.com/{source}/{job_id}/apply",
        apply_email=apply_email,
        location=location,
        description=description or "Machine learning internship. Python, RAG, LLMs, evaluation.",
        employment_type=employment_type,
        is_remote=is_remote,
    )


class FakeAdapter(SubmissionAdapter):
    """Records submissions instead of performing them."""

    name = "fake"

    def __init__(self, config, answers: AnswerBook | None = None):
        super().__init__(config, answers or AnswerBook())
        self.calls: list[str] = []

    def can_submit(self, plan: ApplicationPlan) -> tuple[bool, str]:
        return True, ""

    def submit(self, plan: ApplicationPlan) -> SubmissionResult:
        self.calls.append(plan.posting.stable_id)
        return SubmissionResult(status="submitted", detail="fake submission", adapter=self.name)


def strong_match(score: float = 0.9, matched=("Python", "RAG"), missing=()) -> MatchResult:
    return MatchResult(
        score=score,
        band="strong",
        reasons=["test"],
        coverage=KeywordCoverage(matched=list(matched), missing=list(missing)),
        missing_keywords=list(missing),
    )


def plan_for(p: JobPosting, match: MatchResult | None = None) -> ApplicationPlan:
    return ApplicationPlan(posting=p, match=match or strong_match())
