"""Fact extraction and the "never invent content" validator.

The master profile is the single source of truth. A tailored resume may select,
reorder and re-emphasise its content, but it must not contain a number, an
employer, a date, a metric or a skill that the profile does not state.

The validator is deliberately strict and deterministic:

* every numeric token in generated text must occur in the profile;
* every content word in generated text must occur in the profile vocabulary,
  or be an explicitly allowed function/connective word.

Formatting (LaTeX commands, punctuation, bullets) is stripped before comparison
so that styling choices cannot mask an invented fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Numbers including decimals, percentages, fractions, ranges, version suffixes
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:[ \t]*/[ \t]*\d+)?[ \t]*%?")
# LaTeX commands, braces and math wrappers are formatting, not content.
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z@]+\*?")
_MATH_RE = re.compile(r"\$[^$]*\$")


def strip_formatting(text: str) -> str:
    text = _MATH_RE.sub(" ", text)
    text = _LATEX_CMD_RE.sub(" ", text)
    text = text.replace("\\", " ").replace("{", " ").replace("}", " ")
    text = text.replace("$", " ").replace("&", " ").replace("~", " ")
    return text


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")


def normalize_number(token: str) -> str:
    return re.sub(r"\s+", "", token.replace(",", "")).lower()


def extract_numbers(text: str) -> set[str]:
    raw = _NUMBER_RE.findall(strip_formatting(text))
    out: set[str] = set()
    for tok in raw:
        n = normalize_number(tok)
        out.add(n)
        # A fraction such as 51/51 also contributes its parts.
        if "/" in n:
            a, b = n.split("/", 1)
            out.add(a)
            out.add(b)
    return out


# Function words, connectives and resume-neutral verbs. A connective cannot
# carry a fact on its own; numbers and proper nouns are validated separately.
DEFAULT_ALLOWED_WORDS = frozenset(
    """
    a an the and or of to in on for with by at from as is are was were be been being
    this that these those it its their they them he she his her our we you your i
    using used use through via across into over under while when where which who whom whose
    improving improved improve increase increased increasing reduce reduced reducing
    achieved achieve achieving achieving generated generating built build building
    developed develop developing designed design creating created create led leading
    ensuring ensure ensured enabled enabling delivered delivering authored
    measured measure measuring reported reporting found finding exposed exposing
    high higher highest low lower lowest large larger largest small smaller smallest
    scale large-scale real-world real new novel first best better same different
    quality cost costs performance accuracy integrity data model models tooling
    pipelines pipeline results result outcome outcomes work working team teams
    cross-functional cross functional insight insights report reports actionable
    complex technical logical operational structured rapid robust rigorous
    against versus than then also including include included includes such
    more most less least many much several three two four five six seven eight
    nine ten zero one both each all any some only just even still yet
    end to end state-of-the-art near approximate approximately measured
    """.split()
)


@dataclass
class Violation:
    kind: str
    token: str
    context: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.token!r} ({self.context})"


def content_tokens(text: str) -> list[str]:
    cleaned = strip_formatting(text).lower()
    words = []
    for m in _WORD_RE.finditer(cleaned):
        w = m.group(0).strip(".-")
        if len(w) >= 2 and not w.isdigit():
            words.append(w)
    return words


class FactValidator:
    """Validates generated text against a profile's facts."""

    def __init__(self, profile_text: str, allowed_words: frozenset[str] | None = None):
        self.profile_text = profile_text
        self.profile_numbers = extract_numbers(profile_text)
        self.profile_vocab = set(content_tokens(profile_text))
        self.allowed = DEFAULT_ALLOWED_WORDS | (allowed_words or frozenset())

    def validate(
        self,
        text: str,
        extra_allowed: set[str] | None = None,
        extra_numbers: set[str] | None = None,
    ) -> list[Violation]:
        extra = {w.lower() for w in (extra_allowed or set())}
        allowed_numbers = {normalize_number(n) for n in (extra_numbers or set())}
        violations: list[Violation] = []

        for num in sorted(extract_numbers(text)):
            if num not in self.profile_numbers and num not in allowed_numbers:
                violations.append(Violation("number", num, "not stated in master profile"))

        unknown: set[str] = set()
        for word in content_tokens(text):
            if word in self.profile_vocab or word in self.allowed or word in extra:
                continue
            # Tolerate simple morphological variants of profile vocabulary.
            if _has_stem_in_profile(word, self.profile_vocab):
                continue
            unknown.add(word)
        for word in sorted(unknown):
            violations.append(Violation("unknown-word", word, "absent from master profile vocabulary"))
        return violations

    def is_clean(
        self,
        text: str,
        extra_allowed: set[str] | None = None,
        extra_numbers: set[str] | None = None,
    ) -> bool:
        return not self.validate(text, extra_allowed, extra_numbers)


def _has_stem_in_profile(word: str, vocab: set[str]) -> bool:
    """True when a plural/verb variant shares a substantial stem with the profile."""
    for suffix in ("ing", "es", "s", "ed", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stem = word[: -len(suffix)]
            if stem in vocab:
                return True
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = word[: -len(suffix)]
            for v in vocab:
                if v.startswith(stem) or stem.startswith(v):
                    if min(len(stem), len(v)) >= 4:
                        return True
    return False


# Numbers for emphasis only: not inside an alphanumeric token, so version
# strings like "Qwen2.5-3B" are left intact but "0.155" and "94%" are bolded.
_BOLD_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?:[ \t]*/[ \t]*\d+(?:\.\d+)?)?[ \t]*%?(?![A-Za-z0-9])"
)


def bold_measurements(text: str) -> str:
    """Bold existing measured values without changing a single word.

    Only values already present in the text are wrapped, so this cannot invent
    a metric. Surrounding whitespace is preserved.
    """

    def wrap(raw: str) -> str:
        stripped = raw.strip()
        if not stripped:
            return raw
        lead = raw[: len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip(" \t")) :]
        return f"{lead}\\textbf{{{stripped}}}{trail}"

    parts = re.split(r"(\\[a-zA-Z@]+\*?(?:\{[^{}]*\})?)", text)
    out = []
    for part in parts:
        if part.startswith("\\"):
            out.append(part)
            continue
        out.append(_BOLD_NUMBER_RE.sub(lambda m: wrap(m.group(0)), part))
    return "".join(out)
