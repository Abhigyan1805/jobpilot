"""Parseability check on the compiled PDF.

This does not test whether an "ATS will accept" a resume - that framing is
overstated. What is real and testable is whether the text a human cares about is
*extractable*: columns, tables, images, headers and footers can break text
extraction. We extract the PDF text and assert the standard sections and the
target keywords are present as machine-readable text.
"""

from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path

from jobpilot.htmlutil import clean_whitespace


class TextExtractionError(RuntimeError):
    pass


# Typographic substitutions the LaTeX templates produce from plain source text,
# mapped back to what a user or the profile actually typed. LaTeX turns `'` into
# U+2019 and `--` into U+2013, so a keyword like "Master's" or a date range would
# otherwise false-fail against the extracted text layer. Ported from the
# MIT-licensed upstream ``tools/verify_pdf.py`` (MadsLorentzen/ai-job-search).
TYPOGRAPHIC_FOLDS = str.maketrans(
    {
        "\u2018": "'",  # quoteleft
        "\u2019": "'",  # quoteright (the possessive apostrophe)
        "\u201c": '"',  # quotedblleft
        "\u201d": '"',  # quotedblright
        "\u2013": "-",  # en dash (LaTeX `--`)
        "\u2014": "-",  # em dash (LaTeX `---`)
        "\u00a0": " ",  # no-break space
    }
)


def normalize_text(text: str) -> str:
    """Fold a string for comparison: NFC, typographic punctuation, whitespace.

    NFC covers the pdflatex text layer, which without T1 font encoding stores
    accented letters decomposed (``e`` + U+0300) while the profile types them
    precomposed (U+00E8); both fold to the same string. The fold applies to what
    is compared, never to the raw extraction that is dumped for inspection.
    """
    text = unicodedata.normalize("NFC", text or "").translate(TYPOGRAPHIC_FOLDS)
    return " ".join(text.split())


def extract_pdf_text(pdf_path: str, extractor: str, *, timeout: int = 60) -> str:
    """Extract text via pdftotext (the extractor shipped with the LaTeX engine).

    The extractor is invoked from the PDF's directory with a relative filename
    and writes to stdout, mirroring :func:`jobpilot.resume.compiler.compile_tex`.
    That matters when the engine is a Windows ``pdftotext.exe`` launched from
    WSL: an absolute Linux path passed as an argument is not translated and the
    Windows process cannot open it, whereas a relative filename resolved against
    the working directory is. Writing to stdout (``-``) avoids needing a second
    path that a Windows process also could not reach. stdout is decoded as UTF-8
    with ``errors="replace"`` because pdftotext always emits UTF-8 while the
    invoking process locale need not be, so a strict locale decode of a non-ASCII
    resume would otherwise raise ``UnicodeDecodeError``.
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise TextExtractionError(f"pdf not found: {pdf_path}")
    try:
        proc = subprocess.run(
            [extractor, "-layout", pdf.name, "-"],
            cwd=str(pdf.parent),
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise TextExtractionError(f"text extractor not found: {extractor}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TextExtractionError(f"text extraction timed out after {timeout}s") from exc
    if not proc.stdout:
        raise TextExtractionError(
            f"text extraction failed: {(proc.stderr or proc.stdout or '')[-500:]}"
        )
    return proc.stdout


def count_pages(text: str) -> int:
    """Count pages in pdftotext output by its form-feed page separators.

    pdftotext terminates every page with a form feed (``\\f``), including the
    last, so the feed count is the page count; when a producer omits the final
    separator we still count the trailing page. Deterministic and dependency-free
    (the extractor is already invoked for the parseability check).
    """
    if not text:
        return 0
    feeds = text.count("\f")
    if feeds == 0:
        return 1
    return feeds if text.endswith("\f") else feeds + 1


def check_parseability(
    text: str,
    *,
    required_sections: list[str],
    required_keywords: list[str],
    required_contact: list[str] | None = None,
    min_keyword_survival: float = 0.5,
) -> tuple[bool, str]:
    """Whether the extracted text carries the required sections, keywords and contact.

    Both sides of every comparison are folded with :func:`normalize_text` (NFC
    plus LaTeX's typographic substitutions) so a genuinely parseable resume is
    not false-failed on a curly apostrophe or an en-dash. ``text`` itself is the
    raw extraction and is never rewritten here, so any dump stays what an ATS
    would actually see.
    """
    flat = normalize_text(clean_whitespace(text)).lower()
    missing_sections = [s for s in required_sections if normalize_text(s).lower() not in flat]

    keywords = [k for k in required_keywords if k]
    present = [k for k in keywords if normalize_text(clean_whitespace(k)).lower() in flat]
    if keywords:
        survival = len(present) / len(keywords)
    else:
        survival = 1.0

    contacts = [c for c in (required_contact or []) if c]
    missing_contact = [c for c in contacts if normalize_text(c).lower() not in flat]

    problems = []
    if missing_sections:
        problems.append(f"missing sections: {', '.join(missing_sections)}")
    if missing_contact:
        problems.append(f"missing contact details: {', '.join(missing_contact)}")
    if keywords and survival < min_keyword_survival:
        missing_kw = [k for k in keywords if k not in present]
        problems.append(
            f"keyword survival {survival:.0%} below {min_keyword_survival:.0%}; "
            f"unextractable: {', '.join(missing_kw[:10])}"
        )
    if problems:
        return False, "; ".join(problems)
    return True, f"sections ok; contact ok; keyword survival {survival:.0%}"
