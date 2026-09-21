"""Submission adapter interface.

There is deliberately no generic "fill any web form" adapter. Where a board has
no stable public submission path, the pipeline does not improvise - it routes
the application to the review queue with everything needed to approve it in one
click.
"""

from __future__ import annotations

import re
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path

from jobpilot.answers import AnswerBook
from jobpilot.config import Config
from jobpilot.models import ApplicationPlan, JobPosting, SubmissionResult

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\Z")


class SubmissionAdapter(ABC):
    name: str = "none"
    #: Form fields this adapter must have answers for before it may submit.
    required_fields: list[str] = []

    def __init__(self, config: Config, answers: AnswerBook):
        self.config = config
        self.answers = answers

    def can_submit(self, plan: ApplicationPlan) -> tuple[bool, str]:
        missing = self.answers.missing(self.required_fields)
        if missing:
            return False, f"required field(s) not answerable from profile/answers: {', '.join(missing)}"
        return True, ""

    @abstractmethod
    def submit(self, plan: ApplicationPlan) -> SubmissionResult:
        """Submit one application. Callers handle dedupe and the daily cap."""


class NoPublicPathAdapter(SubmissionAdapter):
    """Sentinel for boards without a stable public submission path."""

    name = "no_public_path"

    def __init__(self, config: Config, answers: AnswerBook, reason: str = ""):
        super().__init__(config, answers)
        self.reason = reason or "no stable public submission path; requires review"

    def can_submit(self, plan: ApplicationPlan) -> tuple[bool, str]:
        return False, self.reason

    def submit(self, plan: ApplicationPlan) -> SubmissionResult:  # pragma: no cover - never called
        return SubmissionResult(status="manual_required", detail=self.reason, adapter=self.name)


class EmailAdapter(SubmissionAdapter):
    """Submit by emailing the posting's application address.

    Disabled unless the config supplies SMTP settings. The recipient must be an
    explicit, structured ``apply_email`` supplied by the source (optionally
    narrowed by ``apply.submission.email_allowlist``); an address is never
    scraped from free-text posting body, so a stray support/privacy address in a
    JD can never receive the resume.
    """

    name = "email"
    required_fields = ["email"]

    def can_submit(self, plan: ApplicationPlan) -> tuple[bool, str]:
        recipient, reason = self._recipient(plan.posting)
        if not recipient:
            return False, reason
        smtp = self.config.apply.submission.get("smtp", {})
        if not smtp.get("host"):
            return False, "email submission not configured (apply.submission.smtp.host)"
        if not plan.resume or not plan.resume.pdf_path:
            return False, "no compiled resume PDF to attach"
        return super().can_submit(plan)

    def submit(self, plan: ApplicationPlan) -> SubmissionResult:
        recipient, reason = self._recipient(plan.posting)
        if not recipient:
            return SubmissionResult(status="failed", detail=reason, adapter=self.name)
        smtp_cfg = self.config.apply.submission.get("smtp", {})
        sender = smtp_cfg.get("from") or self.answers.resolve("email")
        company = plan.posting.company or "your team"
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = f"Application: {plan.posting.title} - {company}"
        msg.set_content(
            plan.cover.text if plan.cover and plan.cover.text
            else "Please find my application and resume attached."
        )
        if plan.resume and plan.resume.pdf_path:
            pdf = Path(plan.resume.pdf_path)
            if pdf.exists():
                msg.add_attachment(
                    pdf.read_bytes(), maintype="application", subtype="pdf", filename="resume.pdf"
                )
        try:
            with smtplib.SMTP(smtp_cfg["host"], int(smtp_cfg.get("port", 587)), timeout=30) as server:
                if smtp_cfg.get("starttls", True):
                    server.starttls()
                if smtp_cfg.get("username"):
                    server.login(smtp_cfg["username"], smtp_cfg.get("password", ""))
                server.send_message(msg)
        except Exception as exc:  # noqa: BLE001 - reported as a failed attempt
            return SubmissionResult(status="failed", detail=f"email send failed: {exc}", adapter=self.name)
        return SubmissionResult(
            status="submitted",
            detail=f"emailed application to {recipient}",
            adapter=self.name,
            evidence={"recipient": recipient, "subject": msg["Subject"]},
        )

    def _recipient(self, posting: JobPosting) -> tuple[str, str]:
        address = (posting.apply_email or "").strip()
        if not address or not EMAIL_RE.fullmatch(address):
            return "", "no authorized application email for this posting"
        allowlist = [
            str(entry).strip().lower()
            for entry in (self.config.apply.submission.get("email_allowlist") or [])
            if str(entry).strip()
        ]
        if allowlist and address.lower() not in allowlist:
            return "", f"application email {address!r} is not in apply.submission.email_allowlist"
        return address, ""


def build_adapter(config: Config, answers: AnswerBook) -> SubmissionAdapter:
    kind = (config.apply.adapter or "auto").lower()
    if kind == "email":
        return EmailAdapter(config, answers)
    if kind == "none":
        return NoPublicPathAdapter(config, answers)
    from jobpilot.applying.ats import AtsAdapter

    return AtsAdapter(config, answers)
