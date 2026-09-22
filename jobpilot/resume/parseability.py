"""Parseability check on the compiled PDF.

This does not test whether an "ATS will accept" a resume - that framing is
overstated. What is real and testable is whether the text a human cares about is
*extractable*: columns, tables, images, headers and footers can break text
extraction. We extract the PDF text and assert the standard sections and the
target keywords are present as machine-readable text.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from jobpilot.htmlutil import clean_whitespace


class TextExtractionError(RuntimeError):
    pass


def extract_pdf_text(pdf_path: str, extractor: str, *, timeout: int = 60) -> str:
    """Extract text via pdftotext (the extractor shipped with the LaTeX engine).

    The extractor is invoked from the PDF's directory with a relative filename
    and writes to stdout, mirroring :func:`jobpilot.resume.compiler.compile_tex`.
    That matters when the engine is a Windows ``pdftotext.exe`` launched from
    WSL: an absolute Linux path passed as an argument is not translated and the
    Windows process cannot open it, whereas a relative filename resolved against
    the working directory is. Writing to stdout (``-``) avoids needing a second
    path that a Windows process also could not reach.
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


def check_parseability(
    text: str,
    *,
    required_sections: list[str],
    required_keywords: list[str],
    min_keyword_survival: float = 0.5,
) -> tuple[bool, str]:
    flat = clean_whitespace(text).lower()
    missing_sections = [s for s in required_sections if s.lower() not in flat]

    keywords = [k for k in required_keywords if k]
    present = [k for k in keywords if clean_whitespace(k).lower() in flat]
    if keywords:
        survival = len(present) / len(keywords)
    else:
        survival = 1.0

    problems = []
    if missing_sections:
        problems.append(f"missing sections: {', '.join(missing_sections)}")
    if keywords and survival < min_keyword_survival:
        missing_kw = [k for k in keywords if k not in present]
        problems.append(
            f"keyword survival {survival:.0%} below {min_keyword_survival:.0%}; "
            f"unextractable: {', '.join(missing_kw[:10])}"
        )
    if problems:
        return False, "; ".join(problems)
    return True, f"sections ok; keyword survival {survival:.0%}"
