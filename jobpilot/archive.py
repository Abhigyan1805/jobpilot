"""Archive the exact submitted or approved materials to disk.

After a submission (auto-applied) or a manual approval, the resume, cover
letter, their LaTeX sources and the posting text are copied into
``<output.dir>/applications/<company>-<title>-<hash>/``. The archived copy is
what was actually sent, so an existing file is never overwritten by a fresher
draft; the archive is idempotent and safe to call again after an outcome update.

This is deterministic file I/O only: no model, no network. A dead posting URL is
never reconstructed from memory - the posting text comes from the local store.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from jobpilot.review import safe_filename
from jobpilot.store import Store


def _copy_if_absent(source: str, dest: Path) -> bool:
    if not source or dest.exists():
        return False
    src = Path(source)
    if not src.exists():
        return False
    shutil.copy2(src, dest)
    return True


def _posting_markdown(posting, app_row) -> str:
    if posting is None:
        return (
            f"# {app_row['title'] or ''} - {app_row['company'] or ''}\n\n"
            "Posting text unavailable (not in the local store).\n"
        )
    lines = [
        f"# {posting['title'] or ''} - {posting['company'] or ''}",
        "",
        f"- Source: {posting['source']}",
        f"- Location: {posting['location'] or ''}",
        f"- Employment type: {posting['employment_type'] or ''}",
        f"- Published: {posting['published_at'] or ''}",
        f"- Deadline: {posting['deadline'] or ''}",
        f"- URL: {posting['url'] or ''}",
        f"- Apply: {posting['apply_url'] or ''}",
        "",
        "## Description",
        "",
        posting["description"] or "(no description captured)",
        "",
    ]
    return "\n".join(lines)


def _write_outcome(base: Path, app_row) -> None:
    outcome = (app_row["outcome"] or "").strip()
    status = (app_row["status"] or "").strip()
    lines = [
        f"# Outcome: {app_row['company'] or ''} - {app_row['title'] or ''}",
        "",
        f"**Status:** {outcome or status or 'in_progress'}",
        f"**Submitted:** {app_row['submitted_at'] or ''}",
        f"**Reminders sent:** {int(app_row['reminders'] or 0)}",
        "",
        "## Notes",
        "",
        (app_row["notes"] or "").strip() or "(none)",
        "",
        f"_Archived {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}._",
        "",
    ]
    (base / "outcome.md").write_text("\n".join(lines), encoding="utf-8")


def archive_application(store: Store, config, app_row) -> str:
    """Archive one application's materials; return the archive directory.

    ``app_row`` is a row from ``applications``. Existing archived files are left
    untouched, so re-running after an outcome update only refreshes ``outcome.md``.
    """
    stable_id = app_row["stable_id"]
    posting = store.get_posting(stable_id)
    company = app_row["company"] or (posting["company"] if posting else "")
    title = app_row["title"] or (posting["title"] if posting else "")
    slug = safe_filename(f"{company}-{title}", max_length=48)
    digest = hashlib.sha1(stable_id.encode("utf-8")).hexdigest()[:10]
    base = Path(config.resolve(config.output.dir)) / "applications" / f"{slug}-{digest}"
    base.mkdir(parents=True, exist_ok=True)

    _copy_if_absent(app_row["resume_pdf"], base / "resume.pdf")
    _copy_if_absent(app_row["resume_tex"], base / "resume.tex")
    _copy_if_absent(app_row["cover_pdf"], base / "cover_letter.pdf")
    _copy_if_absent(app_row["cover_tex"], base / "cover_letter.tex")

    posting_file = base / "job_posting.md"
    if not posting_file.exists():
        posting_file.write_text(_posting_markdown(posting, app_row), encoding="utf-8")

    _write_outcome(base, app_row)
    store.set_archive_dir(stable_id, str(base))
    return str(base)
