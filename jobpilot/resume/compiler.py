"""Compile a generated .tex into a PDF with the configured LaTeX engine."""

from __future__ import annotations

import subprocess
from pathlib import Path


class CompileError(RuntimeError):
    def __init__(self, message: str, log: str = ""):
        super().__init__(message)
        self.log = log


def compile_tex(
    tex_path: str,
    engine: str,
    *,
    timeout: int = 120,
    runs: int = 2,
) -> tuple[str, str]:
    """Compile tex_path next to itself; return (pdf_path, log_tail).

    The engine is invoked from the .tex directory with a relative filename so
    that a Windows engine launched from WSL resolves paths correctly. Its
    stdout/stderr is decoded as UTF-8 with ``errors="replace"`` because the
    Windows engine's console output is not guaranteed to be UTF-8: a document
    containing non-ASCII text (a posting title in another script was observed)
    makes the engine emit bytes that are invalid UTF-8, and a strict decode
    raised ``UnicodeDecodeError`` before the real compile result could be read.
    """
    tex = Path(tex_path)
    if not tex.exists():
        raise CompileError(f"tex file not found: {tex_path}")
    workdir = tex.parent
    log_tail = ""
    last_err = ""
    for _ in range(max(1, runs)):
        try:
            proc = subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error", tex.name],
                cwd=str(workdir),
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise CompileError(f"latex engine not found: {engine}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CompileError(f"latex engine timed out after {timeout}s", log=_read_log(tex)) from exc

        log_tail = _read_log(tex) or (proc.stdout or "")[-2000:]
        if proc.returncode == 0:
            pdf = tex.with_suffix(".pdf")
            if pdf.exists():
                return str(pdf), log_tail
            last_err = "engine returned success but no PDF was produced"
        else:
            last_err = f"engine exited {proc.returncode}"
        # One retry helps when a first pass must write aux files.
    raise CompileError(last_err or "compilation failed", log=log_tail)


def _read_log(tex: Path) -> str:
    log = tex.with_suffix(".log")
    if not log.exists():
        return ""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-40:])
