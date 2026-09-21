"""Review queue: uncertain matches and no-public-path applications.

Each queued item carries everything needed to approve it in one click: the
generated resume PDF, the cover letter PDF and the direct link. A packet
directory also holds a machine-readable ``packet.json`` for export.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from jobpilot.models import ApplicationPlan
from jobpilot.store import Store


def safe_filename(text: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "").strip("-")
    return slug[:max_length] or "item"


def build_packet(plan: ApplicationPlan, out_dir: str) -> str:
    """Copy artifacts into a per-application packet directory; return its path."""
    posting = plan.posting
    slug = safe_filename(f"{posting.source}-{posting.company}-{posting.title}", max_length=48)
    digest = hashlib.sha1(posting.stable_id.encode("utf-8")).hexdigest()[:10]
    name = f"{slug}-{digest}"
    packet_dir = Path(out_dir) / "review" / name
    packet_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    if plan.resume and plan.resume.pdf_path and Path(plan.resume.pdf_path).exists():
        dest = packet_dir / "resume.pdf"
        shutil.copy2(plan.resume.pdf_path, dest)
        artifacts["resume_pdf"] = str(dest)
    if plan.resume and plan.resume.tex_path and Path(plan.resume.tex_path).exists():
        dest = packet_dir / "resume.tex"
        shutil.copy2(plan.resume.tex_path, dest)
        artifacts["resume_tex"] = str(dest)
    if plan.cover and plan.cover.pdf_path and Path(plan.cover.pdf_path).exists():
        dest = packet_dir / "cover_letter.pdf"
        shutil.copy2(plan.cover.pdf_path, dest)
        artifacts["cover_pdf"] = str(dest)
    if plan.cover and plan.cover.tex_path and Path(plan.cover.tex_path).exists():
        dest = packet_dir / "cover_letter.tex"
        shutil.copy2(plan.cover.tex_path, dest)
        artifacts["cover_tex"] = str(dest)

    packet = {
        "source": posting.source,
        "stable_id": posting.stable_id,
        "company": posting.company,
        "title": posting.title,
        "url": posting.url,
        "apply_url": posting.apply_url or posting.url,
        "location": posting.location,
        "score": round(plan.match.score, 4),
        "band": plan.match.band,
        "reasons": plan.match.reasons,
        "missing_keywords": plan.missing_keywords,
        "red_flags": plan.red_flags,
        "review_reason": plan.review_reason,
        "artifacts": artifacts,
    }
    (packet_dir / "packet.json").write_text(json.dumps(packet, indent=2), encoding="utf-8")

    link = posting.apply_url or posting.url
    if link:
        (packet_dir / "apply_link.txt").write_text(link + "\n", encoding="utf-8")
    return str(packet_dir)


def queue_plan(store: Store, plan: ApplicationPlan, out_dir: str) -> str:
    packet_dir = build_packet(plan, out_dir)
    store.enqueue_review(plan, packet_dir=packet_dir)
    return packet_dir


def export_queue(store: Store, out_path: str, status: str = "pending") -> str:
    rows = store.list_review(status=status)
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "stable_id": row["stable_id"],
                "source": row["source"],
                "company": row["company"],
                "title": row["title"],
                "apply_url": row["apply_url"],
                "score": row["score"],
                "reasons": json.loads(row["reasons"] or "[]"),
                "gaps": json.loads(row["gaps"] or "[]"),
                "resume_pdf": row["resume_pdf"],
                "cover_pdf": row["cover_pdf"],
                "packet_dir": row["packet_dir"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
        )
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".jsonl":
        payload = "\n".join(json.dumps(i) for i in items) + ("\n" if items else "")
    elif path.suffix.lower() == ".md":
        payload = _to_markdown(items)
    else:
        payload = json.dumps(items, indent=2)
    path.write_text(payload, encoding="utf-8")
    return str(path)


def _to_markdown(items: list[dict]) -> str:
    lines = ["# Jobpilot review queue", ""]
    for item in items:
        lines.append(f"## {item['company']} - {item['title']} (score {item['score']})")
        lines.append(f"- source: {item['source']}")
        lines.append(f"- apply: {item['apply_url']}")
        lines.append(f"- resume: {item['resume_pdf']}")
        lines.append(f"- cover: {item['cover_pdf']}")
        if item["gaps"]:
            lines.append(f"- gaps: {', '.join(item['gaps'][:15])}")
        lines.append("")
    return "\n".join(lines)
