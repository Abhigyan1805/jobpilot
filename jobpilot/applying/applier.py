"""Apply orchestration with the mandatory guardrails.

Order of guards (all checked before any submission):

1. LinkedIn postings are *never* submitted; they always go to the review queue.
2. A plan flagged during generation is never auto-submitted.
3. A posting whose Jan-Jun window is unconfirmed is never auto-submitted unless
   ``filter.allow_unknown_window`` is set; it goes to the review queue.
4. Only strong matches are auto-submitted.
5. Deduplicate on a stable job id; an attempt is recorded **before** submitting.
6. Never submit a form with a required field that cannot be answered.
7. Enforce a configurable daily cap.
8. Persist a durable record of every attempt and its outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobpilot.applying.base import SubmissionAdapter
from jobpilot.config import Config
from jobpilot.filtering import review_only_reasons
from jobpilot.models import ApplicationPlan
from jobpilot.review import queue_plan
from jobpilot.store import Store
from jobpilot.window import classify_window


@dataclass
class ApplyOutcome:
    action: str
    status: str
    reason: str = ""
    app_id: int | None = None

    def to_dict(self) -> dict:
        return {"action": self.action, "status": self.status, "reason": self.reason, "app_id": self.app_id}


class Applier:
    def __init__(self, store: Store, config: Config, adapter: SubmissionAdapter, out_dir: str):
        self.store = store
        self.config = config
        self.adapter = adapter
        self.out_dir = out_dir

    def process(self, plan: ApplicationPlan, *, dry_run: bool = False) -> ApplyOutcome:
        posting = plan.posting

        # Guard 1: LinkedIn is review-only, always.
        if posting.source == "linkedin":
            plan.requires_review = True
            self._add_reason(plan, "LinkedIn: discovered and tailored, but never auto-submitted (captain applies)")
            return self._to_review(plan, "linkedin_review", "linkedin")

        # Guard 1b: a plan flagged during generation (compile failure,
        # no-invention, unparseable PDF) is never auto-submitted.
        if plan.requires_review:
            if not plan.review_reason:
                plan.review_reason = "flagged for review by generation checks"
            return self._to_review(plan, "requires_review", "generation")

        # Guard 1c: an unconfirmed Jan-Jun window is never auto-applied unless
        # the user explicitly loosened it. The posting is still scored and
        # queued for one-click review.
        if not self.config.filter.allow_unknown_window:
            window = classify_window(posting.searchable_text(), self.config.filter)
            if window.overlaps is None:
                self._add_reason(
                    plan, "Jan-Jun window unconfirmed; review before applying"
                )
                return self._to_review(plan, "window_review", "window")

        # Guard 2: only strong matches auto-apply.
        if plan.match.band != "strong":
            self._add_reason(
                plan,
                f"score {plan.match.score:.2f} below strong-match threshold "
                f"{self.config.match.strong_threshold:.2f}",
            )
            return self._to_review(plan, "shortlist_review", "match")

        # Guard 2b: an ambiguous classification (a work-authorization restriction
        # or a full-time cue stated only in the description) is never
        # auto-applied. The posting is still scored and queued for review.
        blockers = review_only_reasons(posting, self.config.filter)
        if blockers:
            for blocker in blockers:
                self._add_reason(plan, blocker)
            return self._to_review(plan, "filter_review", "filter")

        if not self.config.apply.enabled:
            self._add_reason(plan, "auto-apply disabled by config")
            return self._to_review(plan, "review", "config")

        if not self.config.apply.auto_apply_strong:
            self._add_reason(plan, "auto-apply of strong matches disabled by config (apply.auto_apply_strong)")
            return self._to_review(plan, "review", "config")

        # Guard 3 (dedupe): never touch a posting already recorded.
        existing = self.store.submitted_or_attempted(posting.stable_id)
        if existing is not None:
            plan.review_reason = f"already recorded as {existing['status']}"
            return ApplyOutcome("skip", "duplicate", plan.review_reason)

        # Guard 4: required fields must be answerable.
        ok, reason = self.adapter.can_submit(plan)
        if not ok:
            self._add_reason(plan, reason)
            return self._to_review(plan, "manual_required", "no_channel")

        # Guard 5: daily cap.
        cap = int(self.config.apply.daily_cap)
        used = self.store.attempts_today()
        if used >= cap:
            self._add_reason(plan, f"daily cap reached ({used}/{cap})")
            self.store.record_attempt(posting.stable_id, adapter=self.adapter.name, status="capped", detail=plan.review_reason)
            return self._to_review(plan, "capped", "capped")

        # Dry run: record intent, never submit.
        if dry_run:
            app_id = self.store.create_application(plan, status="dry_run", mode="dry_run", adapter=self.adapter.name)
            self.store.record_attempt(
                posting.stable_id, adapter=self.adapter.name, status="dry_run", detail="dry run; not submitted"
            )
            return ApplyOutcome("dry_run", "dry_run", "would auto-apply (dry run)", app_id)

        # Guard 3 + 6: record the attempt *before* submitting.
        app_id = self.store.create_application(plan, status="submitting", mode="auto", adapter=self.adapter.name)
        self.store.record_attempt(posting.stable_id, adapter=self.adapter.name, status="submitting", detail="submission started")

        try:
            result = self.adapter.submit(plan)
        except Exception as exc:  # noqa: BLE001 - surface as a failed attempt, never crash the run
            self.store.record_attempt(posting.stable_id, adapter=self.adapter.name, status="failed", detail=str(exc))
            self.store.update_application(app_id, status="failed", error=str(exc))
            return ApplyOutcome("submit", "failed", str(exc), app_id)

        self.store.record_attempt(
            posting.stable_id, adapter=self.adapter.name, status=result.status, detail=result.detail
        )
        if result.status == "submitted":
            self.store.update_application(app_id, status="submitted", outcome=result.detail)
        else:
            self.store.update_application(app_id, status="failed", error=result.detail)
        return ApplyOutcome("submit", result.status, result.detail, app_id)

    def _to_review(self, plan: ApplicationPlan, status: str, reason: str) -> ApplyOutcome:
        app_id = self.store.create_application(
            plan,
            status="manual_required",
            mode="review",
            adapter=self.adapter.name,
            review_reason=reason,
        )
        queue_plan(self.store, plan, self.out_dir)
        return ApplyOutcome("review", status, plan.review_reason, app_id)

    @staticmethod
    def _add_reason(plan: ApplicationPlan, reason: str) -> None:
        if reason:
            plan.review_reason = f"{plan.review_reason}; {reason}" if plan.review_reason else reason
