"""Submission to the hosted application endpoints of supported ATS boards.

Greenhouse and Lever publish a per-posting, unauthenticated application
endpoint. This adapter maps the master profile and the structured answers file
to the fields each board's form expects, attaches the compiled resume PDF and
POSTs it as ``multipart/form-data``. Any board with no recognised public
application endpoint, or any application missing a required answer, is refused
here and routed to the review queue - no endpoint is ever improvised.

The HTTP transport is injectable so the request that would be sent can be
verified without performing a real application.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from jobpilot.answers import AnswerBook
from jobpilot.applying.base import SubmissionAdapter
from jobpilot.config import Config
from jobpilot.models import ApplicationPlan, JobPosting, SubmissionResult

#: (url, form fields, files) -> (http status, response body). May raise.
Transport = Callable[[str, dict[str, str], dict[str, tuple[str, bytes, str]]], tuple[int, str]]

DEFAULT_HEADERS = {
    "User-Agent": "jobpilot/0.1 (application submission; contact: see config)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

_GH_EMBED_RE = re.compile(r"greenhouse\.io/embed/job_app", re.IGNORECASE)
_GH_JOB_RE = re.compile(
    r"greenhouse\.io/(?P<token>[^/?#]+)/jobs/(?P<jid>\d+)", re.IGNORECASE
)
_LEVER_RE = re.compile(
    r"lever\.co/(?P<site>[^/?#]+)/(?P<posting>[^/?#]+)", re.IGNORECASE
)

REQUIRED_FIELDS: dict[str, list[str]] = {
    "greenhouse": ["first_name", "last_name", "email"],
    "lever": ["name", "email"],
}


@dataclass
class _Prepared:
    board: str
    endpoint: str
    fields: dict[str, str]
    pdf_path: str


def _encode_multipart(
    fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        if value == "":
            continue
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, (filename, data, content_type) in files.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
            + data
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _http_post_multipart(
    url: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    timeout: float = 60.0,
) -> tuple[int, str]:
    body, content_type = _encode_multipart(fields, files)
    headers = dict(DEFAULT_HEADERS)
    headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _board_for(posting: JobPosting) -> str | None:
    source = (posting.source or "").lower()
    if source in REQUIRED_FIELDS:
        return source
    urls = f"{posting.apply_url or ''} {posting.url or ''}"
    if "greenhouse.io" in urls:
        return "greenhouse"
    if "lever.co" in urls:
        return "lever"
    return None


def _endpoint_for(posting: JobPosting, board: str) -> str:
    for candidate in (posting.apply_url, posting.url):
        if not candidate:
            continue
        stripped = candidate.split("#", 1)[0]
        if board == "greenhouse":
            if _GH_EMBED_RE.search(stripped):
                return stripped
            match = _GH_JOB_RE.search(stripped)
            if match:
                return f"https://boards.greenhouse.io/{match.group('token')}/jobs/{match.group('jid')}"
        else:
            match = _LEVER_RE.search(stripped)
            if match:
                return f"https://jobs.lever.co/{match.group('site')}/{match.group('posting')}/apply"
    return ""


class AtsAdapter(SubmissionAdapter):
    """Unified Greenhouse/Lever public application adapter."""

    name = "ats"

    def __init__(self, config: Config, answers: AnswerBook, transport: Transport | None = None):
        super().__init__(config, answers)
        self.transport = transport or _http_post_multipart

    def can_submit(self, plan: ApplicationPlan) -> tuple[bool, str]:
        prepared, reason = self._prepare(plan)
        return (prepared is not None), reason

    def submit(self, plan: ApplicationPlan) -> SubmissionResult:
        prepared, reason = self._prepare(plan)
        if prepared is None:
            return SubmissionResult(status="failed", detail=reason, adapter=self.name)
        pdf = Path(prepared.pdf_path).read_bytes()
        files = {"resume": ("resume.pdf", pdf, "application/pdf")}
        try:
            status, _body = self.transport(prepared.endpoint, prepared.fields, files)
        except Exception as exc:  # noqa: BLE001 - surfaced as a failed attempt
            return SubmissionResult(
                status="failed", detail=f"{prepared.board} submission failed: {exc}", adapter=self.name
            )
        ok = 200 <= int(status) < 300
        return SubmissionResult(
            status="submitted" if ok else "failed",
            detail=f"{prepared.board} application POST {prepared.endpoint} -> HTTP {status}",
            adapter=self.name,
            evidence={
                "board": prepared.board,
                "endpoint": prepared.endpoint,
                "http_status": int(status),
            },
        )

    def _prepare(self, plan: ApplicationPlan) -> tuple[_Prepared | None, str]:
        posting = plan.posting
        board = _board_for(posting)
        if board is None:
            return None, f"no stable public application endpoint for source {posting.source!r}"
        endpoint = _endpoint_for(posting, board)
        if not endpoint:
            return None, f"could not derive a stable {board} application endpoint from the posting"
        fields = self._fields(board)
        missing = [name for name in REQUIRED_FIELDS[board] if not fields.get(name)]
        if missing:
            return None, f"required field(s) not answerable from profile/answers: {', '.join(missing)}"
        if not (plan.resume and plan.resume.pdf_path and Path(plan.resume.pdf_path).exists()):
            return None, "no compiled resume PDF to attach"
        return _Prepared(board=board, endpoint=endpoint, fields=fields, pdf_path=plan.resume.pdf_path), ""

    def _fields(self, board: str) -> dict[str, str]:
        full_name = self.answers.resolve("name") or self.answers.resolve("full_name") or ""
        email = self.answers.resolve("email") or ""
        phone = self.answers.resolve("phone") or ""
        if board == "greenhouse":
            parts = full_name.split()
            first = self.answers.resolve("first_name") or (parts[0] if parts else "")
            last = self.answers.resolve("last_name") or (" ".join(parts[1:]) if len(parts) > 1 else "")
            return {"first_name": first, "last_name": last, "email": email, "phone": phone}
        return {
            "name": full_name,
            "email": email,
            "phone": phone,
            "org": self.answers.resolve("org") or "",
            "urls[GitHub]": self.answers.resolve("github") or "",
            "urls[LinkedIn]": self.answers.resolve("linkedin") or "",
        }
