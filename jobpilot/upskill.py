"""A deterministic skill-gap heatmap from data jobpilot already stores.

jobpilot persists the keywords a posting wanted that the profile lacked
(``postings.missing_keywords``) and the gaps recorded for each application
(``applications.gaps``). This module aggregates those into a ranked learning
list, weighting each job by ``(1 - score)`` so the roles that exposed the most
gaps count for more. No model is involved: it is a pure tally over the database.

Following the upstream study's rules:

* recorded gaps are used as-is; a missing/empty gaps value contributes nothing
  and is never back-filled from a title or role;
* a job is counted once - a posting that became an application is counted from
  the application record, not twice;
* a job with no score contributes no weight (never treated as 0, which would
  read as the maximum weight).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from jobpilot.store import Store


@dataclass
class SkillGap:
    skill: str
    jobs: int = 0
    weight: float = 0.0
    sources: list[str] = field(default_factory=list)


def _json_list(value) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _gap_weight(score) -> float | None:
    """Weight one job's gaps by ``(1 - score)``; no score contributes nothing."""
    if score is None or isinstance(score, bool):
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, 1.0 - value))


def collect_gaps(store: Store) -> list[SkillGap]:
    """Aggregate stored gaps into a ranked list, highest weight first."""
    tally: dict[str, SkillGap] = {}

    def add(skill: str, weight: float, source: str) -> None:
        entry = tally.setdefault(skill, SkillGap(skill=skill))
        entry.jobs += 1
        entry.weight += weight
        if source not in entry.sources:
            entry.sources.append(source)

    # Applications first: a posting that became an application is counted from
    # the application record, so the same job never contributes twice.
    applied: set[str] = set()
    for row in store.iter_rows("SELECT stable_id, gaps, score FROM applications ORDER BY id DESC"):
        stable_id = row["stable_id"]
        if stable_id in applied:
            continue
        applied.add(stable_id)
        weight = _gap_weight(row["score"])
        if weight is None:
            continue
        for skill in _json_list(row["gaps"]):
            add(skill, weight, "application")

    for row in store.iter_rows("SELECT stable_id, missing_keywords, score FROM postings"):
        if row["stable_id"] in applied:
            continue
        weight = _gap_weight(row["score"])
        if weight is None:
            continue
        for skill in _json_list(row["missing_keywords"]):
            add(skill, weight, "posting")

    gaps = list(tally.values())
    gaps.sort(key=lambda gap: (-gap.weight, -gap.jobs, gap.skill.lower()))
    return gaps


def render_heatmap(gaps: list[SkillGap], *, limit: int = 20) -> str:
    """Render the ranked gap table as plain text."""
    if not gaps:
        return "no recorded skill gaps yet (run the pipeline or `jobpilot run` first)"
    shown = gaps[:limit] if limit and limit > 0 else gaps
    lines = [
        f"{'#':>2}  {'skill':<32} {'jobs':>4}  {'weight':>6}  source",
        f"{'-'*2}  {'-'*32} {'-'*4}  {'-'*6}  {'-'*12}",
    ]
    for index, gap in enumerate(shown, start=1):
        sources = ",".join(sorted(gap.sources))
        lines.append(
            f"{index:>2}  {gap.skill[:32]:<32} {gap.jobs:>4}  {gap.weight:>6.2f}  {sources}"
        )
    if len(gaps) > len(shown):
        lines.append(f"... {len(gaps) - len(shown)} more")
    return "\n".join(lines)
