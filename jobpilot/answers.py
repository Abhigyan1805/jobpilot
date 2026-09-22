"""Known answers for application form fields.

Answers are user-supplied in a TOML file (never in source, never committed).
The book can also resolve fields directly from the master profile. Anything it
cannot resolve is reported as missing, and a form with a missing required field
is never submitted.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jobpilot.profile import Profile


@dataclass
class AnswerBook:
    answers: dict[str, str] = field(default_factory=dict)
    profile: Profile | None = None

    @classmethod
    def load(cls, path: str | Path | None, profile: Profile | None = None) -> "AnswerBook":
        data: dict[str, str] = {}
        if path:
            p = Path(path)
            if p.exists():
                with p.open("rb") as fh:
                    raw = tomllib.load(fh)
                table = raw.get("answers", raw)
                data = {
                    str(k): str(v)
                    for k, v in table.items()
                    if isinstance(v, (str, int, float, bool))
                }
        return cls(answers=data, profile=profile)

    def resolve(self, field_name: str) -> str | None:
        key = field_name.strip().lower()
        if key in self.answers:
            return self.answers[key]
        if not self.profile:
            return None
        c = self.profile.contact
        name_parts = self.profile.name.split() if self.profile.name else []
        mapping = {
            "email": c.get("email"),
            "e-mail": c.get("email"),
            "phone": c.get("phone"),
            "phone_number": c.get("phone"),
            "full_name": self.profile.name,
            "name": self.profile.name,
            "first_name": name_parts[0] if name_parts else None,
            "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else None,
            "linkedin": c.get("linkedin"),
            "github": c.get("github"),
            "org": c.get("org"),
        }
        return mapping.get(key)

    def missing(self, fields: list[str]) -> list[str]:
        return [f for f in fields if not self.resolve(f)]
