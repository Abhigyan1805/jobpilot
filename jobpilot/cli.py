"""Command-line interface.

    python -m jobpilot --config config.toml run --dry-run
    python -m jobpilot --config config.toml run
    python -m jobpilot --config config.toml queue list
    python -m jobpilot --config config.toml queue approve 3
    python -m jobpilot --config config.toml queue export --out review.json
    python -m jobpilot --config config.toml present
    python -m jobpilot --config config.toml link-out list
    python -m jobpilot --config config.toml link-out add --source internshala \
        --url <link> --title "Machine Learning Intern" --company Acme
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jobpilot.archive import archive_application
from jobpilot.config import load_config
from jobpilot.deadline import format_deadline, is_stale, staleness_days
from jobpilot.lifecycle import (
    VALID_OUTCOMES,
    candidate_for,
    followup_candidates,
    followup_template,
    is_final,
    normalize_outcome,
    stale_candidates,
)
from jobpilot.linkout import build_manual_posting, configured_sources
from jobpilot.pipeline import run_manual_pipeline, run_pipeline
from jobpilot.present import run_present
from jobpilot.review import export_queue
from jobpilot.store import Store
from jobpilot.upskill import collect_gaps, render_heatmap


def _load(args):
    config_path = Path(args.config)
    if not config_path.exists():
        print(
            f"config not found: {config_path}\n"
            "Copy config.example.toml to config.toml and set your profile path, sources and thresholds.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return load_config(config_path)


def cmd_run(args) -> int:
    config = _load(args)
    stages = tuple(args.stages.split(",")) if args.stages else ("discover", "match", "tailor", "apply")
    result = run_pipeline(config, dry_run=args.dry_run, stages=stages, limit=args.limit)
    _print_source_outcomes(result)
    print(json.dumps(result.stats, indent=2))
    if args.dry_run:
        print("\ndry run: nothing was submitted.", file=sys.stderr)
    return 0


def cmd_queue(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        if args.queue_command == "list":
            rows = store.list_review(status=args.status)
            if not rows:
                print(f"no {args.status} items")
                return 0
            for row in rows:
                print(
                    f"[{row['id']}] {row['score']:.2f} {row['source']:10s} "
                    f"{row['company']} - {row['title']}"
                )
                deadline = _deadline_label(store, config, row["stable_id"])
                if deadline:
                    print(f"      deadline: {deadline}")
                print(f"      apply: {row['apply_url']}")
                print(f"      resume: {row['resume_pdf']}")
                if row["matched_keywords"]:
                    matched = json.loads(row["matched_keywords"] or "[]")
                    print(f"      matched: {', '.join(matched[:10])}")
                if row["gaps"]:
                    gaps = json.loads(row["gaps"] or "[]")
                    print(f"      gaps: {', '.join(gaps[:10])}")
            return 0
        if args.queue_command in ("approve", "reject"):
            row = store.get_review(args.id)
            if row is None:
                print(f"no review item with id {args.id}", file=sys.stderr)
                return 1
            status = "approved" if args.queue_command == "approve" else "rejected"
            store.decide_review(args.id, status)
            print(f"{status}: {row['company']} - {row['title']}")
            if args.queue_command == "approve":
                _archive_stable_id(store, config, row["stable_id"])
                print(f"apply here: {row['apply_url']}")
                print(f"resume: {row['resume_pdf']}")
                print(f"cover:  {row['cover_pdf']}")
                print("(LinkedIn and no-public-path items are submitted by you, never by the pipeline.)")
            return 0
        if args.queue_command == "export":
            out = args.out or "review_queue.json"
            path = export_queue(store, out, status=args.status)
            print(f"exported {path}")
            return 0
    finally:
        store.close()
    return 0


def cmd_link_out(args) -> int:
    config = _load(args)
    if args.link_command == "list":
        sources = configured_sources(config)
        if not sources:
            print("no link-out sources configured")
            return 0
        print("Manual link-out sources (never scraped or authenticated; browse, then add by hand):")
        for source in sources:
            print(f"  {source.name:12s} {source.label}")
            print(f"      search: {source.search_url}")
            print(f"      why manual: {source.terms_note}")
        print()
        print(
            "Add one you found: jobpilot link-out add --source <name> --url <link> "
            "--title \"...\" --company \"...\" [--description-file jd.txt]"
        )
        return 0

    if args.link_command == "add":
        try:
            description = args.description or ""
            if args.description_file:
                description = Path(args.description_file).read_text(encoding="utf-8")
            posting = build_manual_posting(
                config,
                source=args.source,
                url=args.url,
                title=args.title,
                company=args.company,
                location=args.location,
                description=description,
                job_id=args.job_id,
                employment_type=args.employment_type,
                apply_url=args.apply_url,
                published_at=args.published_at,
            )
        except (ValueError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        result = run_manual_pipeline(config, posting, dry_run=args.dry_run)
        print(json.dumps(result.stats, indent=2))
        if result.stats.get("review_id"):
            print(f"queued review #{result.stats['review_id']} -> {result.stats['packet_dir']}")
            print(f"apply link: {result.stats['apply_url']}")
            print("(manual link-out items are submitted by you, never by the pipeline.)")
        else:
            print("posting was not queued; see reject_reasons above.", file=sys.stderr)
        if args.dry_run:
            print("\ndry run: nothing was submitted.", file=sys.stderr)
        return 0
    return 0


def cmd_present(args) -> int:
    config = _load(args)
    index, selection = run_present(config, out_dir_override=args.out)
    print(f"presented {len(selection.included)} technical match(es)")
    if not selection.included and selection.borderline:
        print(
            f"no technical match cleared the floor; showing "
            f"{len(selection.borderline)} borderline match(es)"
        )
    unstated = getattr(selection, "unstated", [])
    if unstated:
        print(f"stipend not stated (verify separately) for {len(unstated)} match(es)")
    print(f"excluded {len(selection.excluded)} non-technical / low-relevance queued posting(s)")
    print(f"review page: {index}")
    print("nothing was submitted.", file=sys.stderr)
    return 0


def cmd_postings(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        rows = store.list_postings(eligible=args.eligible, min_score=args.min_score)
        for row in rows[: args.limit]:
            extras = _posting_flags(config, row)
            print(
                f"{row['score'] if row['score'] is not None else '-':>5} "
                f"{'elig' if row['eligible'] else 'rej '} "
                f"{row['source']:10s} {row['company']} - {row['title']} "
                f"[{row['window_label'] or '?'}]{extras}"
            )
        print(f"({len(rows)} total)")
    finally:
        store.close()
    return 0


def _posting_flags(config, row) -> str:
    """Deadline urgency/expiry and a staleness flag for one posting row."""
    flags: list[str] = []
    label = format_deadline(
        row["deadline"] if "deadline" in row.keys() else "",
        closing_soon_days=int(config.deadline.closing_soon_days),
    )
    if label:
        flags.append(label)
    age = staleness_days(row["published_at"]) if "published_at" in row.keys() else None
    if age is not None and is_stale(row["published_at"], stale_days=int(config.deadline.stale_days)):
        flags.append(f"stale {age}d")
    return ("  " + " ".join(flags)) if flags else ""


def _deadline_label(store: Store, config, stable_id: str) -> str:
    row = store.get_posting(stable_id)
    if row is None or "deadline" not in row.keys():
        return ""
    return format_deadline(row["deadline"], closing_soon_days=int(config.deadline.closing_soon_days))


def cmd_upskill(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        gaps = collect_gaps(store)
    finally:
        store.close()
    print(render_heatmap(gaps, limit=args.limit))
    return 0


def _resolve_stable_id(store: Store, ref: str) -> str:
    """Resolve a review-queue id, application id or stable id to a stable id."""
    ref = (ref or "").strip()
    if not ref:
        return ""
    # A stable id is accepted verbatim when it is already on record.
    if store.get_posting(ref) is not None or store.latest_application(ref) is not None:
        return ref
    if ":" in ref:
        return ""
    if ref.isdigit():
        review = store.get_review(int(ref))
        if review is not None:
            return review["stable_id"]
        app = store.get_application(int(ref))
        if app is not None:
            return app["stable_id"]
    return ""


def _archive_stable_id(store: Store, config, stable_id: str) -> str:
    row = store.latest_application(stable_id)
    if row is None:
        return ""
    try:
        return archive_application(store, config, row)
    except OSError as exc:
        print(f"warning: could not archive application: {exc}", file=sys.stderr)
        return ""


def _print_application_row(row) -> None:
    print(
        f"[app {row['id']}] {row['company']} - {row['title']} "
        f"status={row['status']} outcome={row['outcome'] or '-'} "
        f"reminders={int(row['reminders'] or 0)}"
    )


def cmd_outcome(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        if not args.id:
            rows = [r for r in store.latest_applications() if not is_final(r["outcome"])]
            if not rows:
                print("no open applications to update")
                return 0
            print("Open applications (pass the id to record an outcome):")
            for row in rows:
                _print_application_row(row)
            return 0

        stable_id = _resolve_stable_id(store, args.id)
        if not stable_id:
            print(f"no review, application or posting found for id {args.id!r}", file=sys.stderr)
            return 1

        status = normalize_outcome(args.status) if args.status else ""
        if status and status not in VALID_OUTCOMES:
            print(
                f"unknown outcome {args.status!r}; expected one of: {', '.join(VALID_OUTCOMES)}",
                file=sys.stderr,
            )
            return 2
        if not status:
            row = store.latest_application(stable_id)
            if row is None:
                print("no application recorded for that posting", file=sys.stderr)
                return 1
            _print_application_row(row)
            return 0

        row = store.set_outcome(stable_id, status, note=args.note)
        if row is None:
            print("no application recorded for that posting", file=sys.stderr)
            return 1
        _archive_stable_id(store, config, stable_id)
        print(f"recorded outcome '{status}' for {row['company']} - {row['title']}")
        return 0
    finally:
        store.close()


def cmd_followups(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        if args.record:
            stable_id = _resolve_stable_id(store, args.record)
            if not stable_id:
                print(f"no application found for id {args.record!r}", file=sys.stderr)
                return 1
            row = store.record_followup(stable_id, note=args.note or "follow-up sent")
            if row is None:
                print(f"no application found for id {args.record!r}", file=sys.stderr)
                return 1
            _archive_stable_id(store, config, stable_id)
            candidate = candidate_for(store, stable_id)
            if candidate is not None:
                print(followup_template(candidate))
                print(f"\nlogged follow-up #{int(candidate.reminders)}")
            return 0

        days = args.days if args.days is not None else int(config.lifecycle.followup_days)
        candidates = followup_candidates(
            store, days=days, max_reminders=int(config.lifecycle.max_reminders)
        )
        if not candidates:
            print(f"no follow-ups due ({days}-day quiet threshold)")
            return 0
        print(f"{len(candidates)} follow-up(s) due (quiet {days}+ days, max {config.lifecycle.max_reminders} reminders):")
        print(f"{'app':>4}  {'quiet':>5}  {'sent':>4}  company - title")
        for candidate in candidates:
            print(
                f"{candidate.app_id:>4}  {candidate.quiet_days:>5}  {candidate.reminders:>4}  "
                f"{candidate.company} - {candidate.title}"
            )
        print("\n-- draft (plain template; nothing is sent) --")
        print(followup_template(candidates[0]))
        print("\nRecord one with: jobpilot followups --record <id>")
        return 0
    finally:
        store.close()


def cmd_stale(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        days = args.days if args.days is not None else int(config.lifecycle.stale_days)
        candidates = stale_candidates(store, days=days)
        if not candidates:
            print(f"no open applications quiet for {days}+ days")
            return 0
        print(f"{len(candidates)} stale application(s) (quiet {days}+ days):")
        print(f"{'app':>4}  {'quiet':>5}  company - title")
        for candidate in candidates:
            print(f"{candidate.app_id:>4}  {candidate.quiet_days:>5}  {candidate.company} - {candidate.title}")
        if not args.write:
            print("\ndry run: pass --write to mark them no_response")
            return 0
        for candidate in candidates:
            store.set_outcome(
                candidate.stable_id,
                "no_response",
                note=f"stale resolved no_response after {candidate.quiet_days} days quiet",
            )
            _archive_stable_id(store, config, candidate.stable_id)
        print(f"\nmarked {len(candidates)} application(s) no_response")
        return 0
    finally:
        store.close()


def _print_source_outcomes(result) -> None:
    if not result.source_outcomes:
        return
    print("sources:")
    for outcome in result.source_outcomes:
        if outcome.ok:
            print(f"  ok      {outcome.source}: {len(outcome.postings)} postings")
        elif outcome.skipped:
            print(f"  skipped {outcome.source}: {outcome.error}")
        else:
            print(f"  failed  {outcome.source}: {outcome.error}")
        for query, count in outcome.query_counts.items():
            if query in outcome.query_errors:
                print(f"            {query}: FAILED ({outcome.query_errors[query]})")
            else:
                print(f"            {query}: {count} new")
        for query, error in outcome.query_errors.items():
            if query not in outcome.query_counts:
                print(f"            {query}: FAILED ({error})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobpilot", description="Internship discovery, tailoring and application pipeline.")
    parser.add_argument("--config", default="config.toml", help="path to the TOML config (default: config.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the full pipeline")
    p_run.add_argument("--dry-run", action="store_true", help="discover, match and tailor without submitting")
    p_run.add_argument("--limit", type=int, default=None, help="max shortlisted postings to tailor")
    p_run.add_argument(
        "--stages",
        default="",
        help="comma-separated stages to run: discover,match,tailor,apply (default all)",
    )
    p_run.set_defaults(func=cmd_run)

    p_queue = sub.add_parser("queue", help="inspect and act on the review queue")
    qsub = p_queue.add_subparsers(dest="queue_command", required=True)
    ql = qsub.add_parser("list")
    ql.add_argument("--status", default="pending")
    qa = qsub.add_parser("approve")
    qa.add_argument("id", type=int)
    qr = qsub.add_parser("reject")
    qr.add_argument("id", type=int)
    qe = qsub.add_parser("export")
    qe.add_argument("--out", default="review_queue.json")
    qe.add_argument("--status", default="pending")
    p_queue.set_defaults(func=cmd_queue)

    p_present = sub.add_parser(
        "present", help="render the queued matches as a browsable HTML review page"
    )
    p_present.add_argument(
        "--out",
        default="",
        help="output directory for index.html (default: [output].dir/[present].out_dir)",
    )
    p_present.set_defaults(func=cmd_present)

    p_upskill = sub.add_parser(
        "upskill", help="rank stored skill gaps into a deterministic learning list"
    )
    p_upskill.add_argument("--limit", type=int, default=20)
    p_upskill.set_defaults(func=cmd_upskill)

    p_outcome = sub.add_parser(
        "outcome", help="record what happened to an application (lifecycle status)"
    )
    p_outcome.add_argument("id", nargs="?", default="", help="review id, application id or stable id")
    p_outcome.add_argument("--status", default="", help=f"one of: {', '.join(VALID_OUTCOMES)}")
    p_outcome.add_argument("--note", default="", help="a short dated note to append")
    p_outcome.set_defaults(func=cmd_outcome)

    p_follow = sub.add_parser(
        "followups", help="list open applications gone quiet and draft a plain follow-up"
    )
    p_follow.add_argument("--days", type=int, default=None, help="quiet threshold (default from config)")
    p_follow.add_argument("--record", default="", help="record a follow-up for this application id")
    p_follow.add_argument("--note", default="", help="note to append when recording")
    p_follow.set_defaults(func=cmd_followups)

    p_stale = sub.add_parser(
        "stale", help="sweep open applications quiet for a long time to no_response"
    )
    p_stale.add_argument("--days", type=int, default=None, help="quiet threshold (default from config)")
    p_stale.add_argument("--write", action="store_true", help="mark the candidates no_response")
    p_stale.set_defaults(func=cmd_stale)

    p_post = sub.add_parser("postings", help="list tracked postings")
    p_post.add_argument("--eligible", action="store_true", default=None)
    p_post.add_argument("--min-score", type=float, default=None)
    p_post.add_argument("--limit", type=int, default=50)
    p_post.set_defaults(func=cmd_postings)

    p_link = sub.add_parser(
        "link-out", help="search links and manual intake for sources that forbid automation"
    )
    lsub = p_link.add_subparsers(dest="link_command", required=True)
    lsub.add_parser("list", help="list configured manual link-out sources")
    ladd = lsub.add_parser("add", help="add a posting found on a link-out source and prepare a review packet")
    ladd.add_argument("--source", required=True, help="link-out source name (see `link-out list`)")
    ladd.add_argument("--url", required=True, help="direct URL of the posting you found")
    ladd.add_argument("--title", required=True)
    ladd.add_argument("--company", required=True)
    ladd.add_argument("--location", default="")
    ladd.add_argument("--description", default="", help="job description text")
    ladd.add_argument("--description-file", default="", help="path to a file holding the job description")
    ladd.add_argument("--job-id", default="", help="stable id; defaults to a hash of --url")
    ladd.add_argument("--employment-type", default="Internship")
    ladd.add_argument("--apply-url", default="")
    ladd.add_argument("--published-at", default="")
    ladd.add_argument("--dry-run", action="store_true", help="prepare the packet without recording a live run")
    p_link.set_defaults(func=cmd_link_out)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
