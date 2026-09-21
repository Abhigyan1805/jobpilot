"""Command-line interface.

    python -m jobpilot --config config.toml run --dry-run
    python -m jobpilot --config config.toml run
    python -m jobpilot --config config.toml queue list
    python -m jobpilot --config config.toml queue approve 3
    python -m jobpilot --config config.toml queue export --out review.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jobpilot.config import load_config
from jobpilot.pipeline import run_pipeline
from jobpilot.review import export_queue
from jobpilot.store import Store


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
                print(f"      apply: {row['apply_url']}")
                print(f"      resume: {row['resume_pdf']}")
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


def cmd_postings(args) -> int:
    config = _load(args)
    store = Store(config.resolve(config.output.database))
    try:
        rows = store.list_postings(eligible=args.eligible, min_score=args.min_score)
        for row in rows[: args.limit]:
            print(
                f"{row['score'] if row['score'] is not None else '-':>5} "
                f"{'elig' if row['eligible'] else 'rej '} "
                f"{row['source']:10s} {row['company']} - {row['title']} [{row['window_label'] or '?'}]"
            )
        print(f"({len(rows)} total)")
    finally:
        store.close()
    return 0


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

    p_post = sub.add_parser("postings", help="list tracked postings")
    p_post.add_argument("--eligible", action="store_true", default=None)
    p_post.add_argument("--min-score", type=float, default=None)
    p_post.add_argument("--limit", type=int, default=50)
    p_post.set_defaults(func=cmd_postings)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
