"""End-to-end pipeline: discover -> filter -> match -> tailor -> apply."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jobpilot.answers import AnswerBook
from jobpilot.applying.applier import Applier, ApplyOutcome
from jobpilot.applying.base import build_adapter
from jobpilot.config import Config
from jobpilot.critique import suggest_red_flags
from jobpilot.cover_letter import CoverLetterGenerator
from jobpilot.discovery import FetchOutcome, discover
from jobpilot.filtering import filter_posting
from jobpilot.lexicon import present_surface_forms
from jobpilot.matching import Matcher
from jobpilot.models import ApplicationPlan, JobPosting
from jobpilot.profile import load_profile
from jobpilot.resume.compiler import CompileError, compile_tex
from jobpilot.resume.generator import ContentInvariantError, ResumeGenerator
from jobpilot.resume.parseability import (
    TextExtractionError,
    check_parseability,
    extract_pdf_text,
)
from jobpilot.store import Store


@dataclass
class PipelineResult:
    stats: dict = field(default_factory=dict)
    source_outcomes: list[FetchOutcome] = field(default_factory=list)
    shorts: list[tuple[JobPosting, object]] = field(default_factory=list)
    outcomes: list[tuple[JobPosting, ApplyOutcome]] = field(default_factory=list)


def run_pipeline(
    config: Config,
    *,
    dry_run: bool = False,
    stages: tuple[str, ...] = ("discover", "match", "tailor", "apply"),
    limit: int | None = None,
    max_pages: int | None = None,
) -> PipelineResult:
    if max_pages is not None:
        config.linkedin.max_pages = max_pages

    out_dir = Path(config.resolve(config.output.dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile(config.resolve(config.profile.path))
    store = Store(config.resolve(config.output.database))
    run_id = store.start_run("dry_run" if dry_run else "live")
    result = PipelineResult()

    try:
        postings: list[JobPosting] = []
        if "discover" in stages:
            postings, source_outcomes = discover(config)
            result.source_outcomes = source_outcomes
        else:
            postings = _postings_from_store(store)

        stats = {
            "discovered": len(postings),
            "sources_ok": sum(1 for o in result.source_outcomes if o.ok),
            "sources_failed": sum(1 for o in result.source_outcomes if o.error and not o.skipped),
            "sources_skipped": sum(1 for o in result.source_outcomes if o.skipped),
            "eligible": 0,
            "shortlisted": 0,
            "strong": 0,
            "tailored": 0,
            "compile_failed": 0,
            "parseability_failed": 0,
            "submitted": 0,
            "queued": 0,
            "duplicates": 0,
            "capped": 0,
            "dry_run": 0,
            "stage": ",".join(stages),
        }

        matcher = Matcher(profile, config)
        eligible: list[tuple[JobPosting, object, object]] = []

        if "match" in stages:
            for posting in postings:
                fr = filter_posting(posting, config.filter)
                store.upsert_posting(
                    posting,
                    eligible=fr.eligible,
                    window_label=fr.window_label,
                    window_confidence=fr.window_confidence,
                    reject_reasons=fr.reject_reasons,
                )
                if not fr.eligible:
                    continue
                m = matcher.match(posting)
                store.save_match(posting.stable_id, m, eligible=True, reject_reasons=[])
                eligible.append((posting, fr, m))
            stats["eligible"] = len(eligible)
        else:
            eligible = _eligible_from_store(store, postings, matcher)

        shorts = [
            (p, m)
            for (p, _fr, m) in eligible
            if m.score >= config.match.shortlist_threshold
        ]
        shorts.sort(key=lambda pm: pm[1].score, reverse=True)
        if limit is not None:
            shorts = shorts[:limit]
        stats["shortlisted"] = len(shorts)
        stats["strong"] = sum(1 for _p, m in shorts if m.band == "strong")
        result.shorts = shorts

        answers = AnswerBook.load(config.resolve(config.apply.answers_file), profile)
        adapter = build_adapter(config, answers)
        applier = Applier(store, config, adapter, str(out_dir))

        if "tailor" in stages or "apply" in stages:
            generator = ResumeGenerator(profile, config)
            cover_gen = CoverLetterGenerator(profile, config)
            for posting, match in shorts:
                plan, outcome = self_contained_tailor_apply(
                    config,
                    posting,
                    match,
                    generator,
                    cover_gen,
                    store,
                    applier,
                    str(out_dir),
                    dry_run=dry_run,
                    do_apply=("apply" in stages),
                )
                stats["tailored"] += 1 if plan.resume else 0
                if plan.resume and not plan.resume.parseability_ok:
                    stats["parseability_failed"] += 1
                if plan.resume and not plan.resume.pdf_path:
                    stats["compile_failed"] += 1
                if outcome is not None:
                    result.outcomes.append((posting, outcome))
                    _count_outcome(stats, outcome)
        stats["queue_pending"] = len(store.list_review("pending"))
        result.stats = stats
        store.finish_run(run_id, stats)
        return result
    finally:
        store.close()


def run_manual_pipeline(
    config: Config,
    posting: JobPosting,
    *,
    dry_run: bool = False,
) -> PipelineResult:
    """Process one posting a human found on a manual-only link-out source.

    Runs the same requirement extraction, matching, tailoring and cover-letter
    generation as the main pipeline. Because the source is manual-only, the
    applier always routes it to the review queue: the pipeline prepares a
    ready-to-apply packet (tailored resume, cover letter and the direct link)
    and the human submits it.
    """
    out_dir = Path(config.resolve(config.output.dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile(config.resolve(config.profile.path))
    store = Store(config.resolve(config.output.database))
    run_id = store.start_run("dry_run" if dry_run else "manual")
    result = PipelineResult()
    stats = {
        "manual": 1,
        "source": posting.source,
        "eligible": 0,
        "shortlisted": 0,
        "strong": 0,
        "tailored": 0,
        "compile_failed": 0,
        "parseability_failed": 0,
        "submitted": 0,
        "queued": 0,
        "review_id": None,
        "packet_dir": "",
        "apply_url": posting.apply_url or posting.url,
        "dry_run": int(dry_run),
    }
    try:
        matcher = Matcher(profile, config)
        fr = filter_posting(posting, config.filter)
        store.upsert_posting(
            posting,
            eligible=fr.eligible,
            window_label=fr.window_label,
            window_confidence=fr.window_confidence,
            reject_reasons=fr.reject_reasons,
        )
        if not fr.eligible:
            stats["reject_reasons"] = fr.reject_reasons
            result.stats = stats
            store.finish_run(run_id, stats)
            return result

        match = matcher.match(posting)
        store.save_match(posting.stable_id, match, eligible=True, reject_reasons=[])
        stats["eligible"] = 1
        stats["score"] = round(match.score, 4)
        stats["band"] = match.band
        stats["shortlisted"] = 1
        stats["strong"] = 1 if match.band == "strong" else 0
        result.shorts = [(posting, match)]

        answers = AnswerBook.load(config.resolve(config.apply.answers_file), profile)
        adapter = build_adapter(config, answers)
        applier = Applier(store, config, adapter, str(out_dir))
        generator = ResumeGenerator(profile, config)
        cover_gen = CoverLetterGenerator(profile, config)

        plan, outcome = self_contained_tailor_apply(
            config,
            posting,
            match,
            generator,
            cover_gen,
            store,
            applier,
            str(out_dir),
            dry_run=dry_run,
            do_apply=True,
        )
        stats["tailored"] += 1 if plan.resume else 0
        if plan.resume and not plan.resume.parseability_ok:
            stats["parseability_failed"] += 1
        if plan.resume and not plan.resume.pdf_path:
            stats["compile_failed"] += 1
        if outcome is not None:
            result.outcomes.append((posting, outcome))
            _count_outcome(stats, outcome)
        row = _find_review(store, posting.stable_id)
        if row is not None:
            stats["review_id"] = row["id"]
            stats["packet_dir"] = row["packet_dir"]
        stats["queue_pending"] = len(store.list_review("pending"))
        result.stats = stats
        store.finish_run(run_id, stats)
        return result
    finally:
        store.close()


def _find_review(store: Store, stable_id: str):
    for row in store.list_review("pending"):
        if row["stable_id"] == stable_id:
            return row
    return None


def self_contained_tailor_apply(
    config: Config,
    posting: JobPosting,
    match,
    generator: ResumeGenerator,
    cover_gen: CoverLetterGenerator,
    store: Store,
    applier: Applier,
    out_dir: str,
    *,
    dry_run: bool,
    do_apply: bool,
) -> tuple[ApplicationPlan, ApplyOutcome | None]:
    plan = ApplicationPlan(
        posting=posting,
        match=match,
        missing_keywords=list(match.missing_keywords),
    )

    # --- tailored resume -------------------------------------------------
    try:
        resume = generator.generate(posting, match, out_dir)
        plan.resume = resume
        pdf_path, log = compile_tex(
            resume.tex_path,
            config.profile.pdflatex,
            timeout=int(config.profile.compile_timeout),
        )
        resume.pdf_path = pdf_path
        resume.compile_log = log
        _run_parseability(config, resume, match, generator.profile)
        if config.match.require_parseable and not resume.parseability_ok:
            plan.requires_review = True
            plan.review_reason = f"parseability check failed: {resume.parseability_detail}"
    except CompileError as exc:
        plan.requires_review = True
        plan.review_reason = f"LaTeX compilation failed: {exc}"
        if plan.resume:
            plan.resume.compile_log = exc.log
    except ContentInvariantError as exc:
        plan.requires_review = True
        plan.review_reason = f"no-invention guard rejected the resume: {exc}"
    except (TextExtractionError, OSError) as exc:
        plan.requires_review = True
        plan.review_reason = f"resume generation error: {exc}"

    # --- cover letter ----------------------------------------------------
    try:
        cover = cover_gen.generate(posting, match, out_dir, generator)
        plan.cover = cover
        if cover.tex_path:
            try:
                pdf_path, _log = compile_tex(
                    cover.tex_path,
                    config.profile.pdflatex,
                    timeout=int(config.profile.compile_timeout),
                )
                cover.pdf_path = pdf_path
            except CompileError:
                pass
    except (ValueError, OSError) as exc:
        plan.requires_review = True
        plan.review_reason = (plan.review_reason + "; " if plan.review_reason else "") + f"cover letter error: {exc}"

    plan.red_flags = suggest_red_flags(posting, match, config)
    plan.gaps = list(match.missing_keywords)

    if not do_apply:
        return plan, None
    outcome = applier.process(plan, dry_run=dry_run)
    return plan, outcome


def _run_parseability(config: Config, resume, match, profile) -> None:
    # Test keyword survival against the profile-present surface forms, not the
    # canonical labels: the no-invention generator can only emit words that are
    # in the profile, so a canonical term supported solely through an alias
    # (e.g. "Communication" via "cross-functional") must be checked as that
    # alias or a perfectly parseable resume is reported unparseable.
    profile_text = " ".join([profile.raw_text, *profile.skill_terms()])
    required_keywords = present_surface_forms(list(match.coverage.matched), profile_text)
    try:
        text = extract_pdf_text(resume.pdf_path, config.profile.pdftotext)
    except TextExtractionError as exc:
        resume.parseability_ok = False
        resume.parseability_detail = str(exc)
        return
    ok, detail = check_parseability(
        text,
        required_sections=list(config.match.required_sections),
        required_keywords=required_keywords,
        min_keyword_survival=float(config.match.min_keyword_survival),
    )
    resume.parseability_ok = ok
    resume.parseability_detail = detail


def _count_outcome(stats: dict, outcome: ApplyOutcome) -> None:
    if outcome.status == "submitted":
        stats["submitted"] += 1
    elif outcome.status == "duplicate":
        stats["duplicates"] += 1
    elif outcome.status == "capped":
        stats["capped"] += 1
    elif outcome.status == "dry_run":
        stats["dry_run"] += 1
    elif outcome.action == "review":
        stats["queued"] += 1


def _postings_from_store(store: Store) -> list[JobPosting]:
    rows = store.list_postings()
    return [
        JobPosting(
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
        for row in rows
    ]


def _eligible_from_store(store: Store, postings: list[JobPosting], matcher: Matcher):
    eligible = []
    for posting in postings:
        row = store.get_posting(posting.stable_id)
        if row is None or not row["eligible"]:
            continue
        m = matcher.match(posting)
        eligible.append((posting, None, m))
    return eligible
