"""Outcome-first ("XYZ") bullet rewriting, strictly bounded by profile facts.

The Google re:Work guidance is: "Accomplished [X], as measured by [Y], by doing
[Z]". When an existing profile bullet already contains an action and a measured
result, we reorder its *existing* clauses so the measured outcome leads. No new
word that carries a fact is introduced, and the result is rejected unless it
passes the strict fact validator - otherwise the original bullet is kept
verbatim.
"""

from __future__ import annotations

import re

from jobpilot.facts import FactValidator

# Result clauses introduced by a gerund, as they commonly appear in the profile.
_RESULT_RE = re.compile(
    r"^(?P<action>.*?)[,;]\s*"
    r"(?P<verb>improving|increasing|reducing|achieving|generating|blocking|saving|"
    r"eliminating|boosting|cutting|forecasting|raising|lowering|delivering)\s+"
    r"(?P<metric>.+?)\.?$",
    re.IGNORECASE,
)

_PAST_TO_GERUND = {
    "developed": "developing",
    "built": "building",
    "engineered": "engineering",
    "designed": "designing",
    "authored": "authoring",
    "measured": "measuring",
    "ran": "running",
    "conducted": "conducting",
    "evaluated": "evaluating",
    "identified": "identifying",
    "optimized": "optimising",
    "optimised": "optimising",
    "validated": "validating",
    "led": "leading",
    "collaborated": "collaborating",
    "created": "creating",
    "blocked": "blocking",
    "forecasted": "forecasting",
    "modeled": "modelling",
    "modelled": "modelling",
    "analyzed": "analysing",
    "analysed": "analysing",
    "enforced": "enforcing",
    "found": "finding",
    "reported": "reporting",
    "swept": "sweeping",
    "exposed": "exposing",
    "implemented": "implementing",
    "established": "establishing",
    "provided": "providing",
    "integrated": "integrating",
    "automated": "automating",
    "scaled": "scaling",
}

_PAST_TO_PRESENT = {
    "improving": "Improved",
    "increasing": "Increased",
    "reducing": "Reduced",
    "achieving": "Achieved",
    "generating": "Generated",
    "blocking": "Blocked",
    "saving": "Saved",
    "eliminating": "Eliminated",
    "boosting": "Boosted",
    "cutting": "Cut",
    "forecasting": "Forecast",
    "raising": "Raised",
    "lowering": "Lowered",
    "delivering": "Delivered",
}


def _to_gerund(action: str) -> str | None:
    first, _, rest = action.partition(" ")
    key = first.replace(",", "").lower()
    if key in _PAST_TO_GERUND:
        return f"{_PAST_TO_GERUND[key]}{(' ' + rest) if rest else ''}"
    return None


def rewrite_bullet(text: str, validator: FactValidator) -> str:
    """Return an XYZ-reordered bullet, or the original when not safely possible."""
    clean = text.strip()
    m = _RESULT_RE.match(clean)
    if not m:
        return text
    action = m.group("action").strip()
    verb = m.group("verb").lower()
    metric = m.group("metric").strip().rstrip(".")
    if not action or not metric:
        return text
    gerund = _to_gerund(action)
    if not gerund:
        return text
    lead = _PAST_TO_PRESENT.get(verb, verb.capitalize())
    candidate = f"{lead} {metric} by {gerund}."
    if validator.is_clean(candidate):
        return candidate
    return text


def has_measurement(text: str) -> bool:
    from jobpilot.facts import extract_numbers

    return bool(extract_numbers(text))
