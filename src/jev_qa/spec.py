"""A QA spec: what to test, what the runner may type, and which endings it accepts back.

The spec is the contract between the author (you, or Claude via the `/qa` skill) and the
runner. Jev never sees anything outside it: every string the runner can type is in `data`,
every ending it can report is in `outcomes`, and `assert` is checked in code on the final page.

    {
      "id": "login",
      "start_url": "https://the-internet.herokuapp.com/login",
      "goal": "Log in with the prepared username and password until the secure area is shown.",
      "data": {"username": "tomsmith", "password": "${DEMO_PASS}"},
      "secrets": ["password"],
      "outcomes": {
        "logged_in":  {"when": "The page heading says 'Secure Area'.", "verdict": "pass"},
        "rejected":   {"when": "A flash message says the password is invalid.", "verdict": "bug"}
      },
      "assert": [{"url_matches": "**/secure"}, {"text_contains": "You logged into a secure area!"}]
    }
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Verdict = Literal["pass", "bug", "needs_human"]

ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SpecError(ValueError):
    """The spec is malformed or its environment is incomplete. Fix that; never a test result."""


class Outcome(BaseModel):
    """An ending the runner may report. Jev judges `when` against the page as a yes/no question."""

    model_config = ConfigDict(extra="forbid")

    when: str = Field(min_length=8, description="One visible fact per sentence.")
    verdict: Verdict
    note: str = ""
    requires_action: bool = Field(
        default=False,
        description="Count this outcome only after an action ran. Use it for 'nothing happened' "
        "bugs, which are also true of the untouched start page.",
    )


class Assertion(BaseModel):
    """An exact, model-free check on the final page. Exactly one field is set."""

    model_config = ConfigDict(extra="forbid")

    url_matches: str | None = None  # glob against the final URL, e.g. "**/secure"
    text_contains: str | None = None  # substring of the visible text, case-insensitive
    element_present: str | None = None  # CSS selector that must match something
    element_absent: str | None = None  # CSS selector that must match nothing

    @model_validator(mode="after")
    def _exactly_one(self) -> Assertion:
        chosen = [k for k, v in self.model_dump().items() if v is not None]
        if len(chosen) != 1:
            raise ValueError(f"an assertion sets exactly one check, got {chosen or 'none'}")
        return self

    @property
    def kind(self) -> str:
        return next(k for k, v in self.model_dump().items() if v is not None)

    @property
    def arg(self) -> str:
        return getattr(self, self.kind)

    def describe(self) -> str:
        return f"{self.kind} {self.arg!r}"


class QaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(pattern=NAME.pattern)
    start_url: str = Field(pattern=r"^https?://\S+$")
    goal: str = Field(min_length=8)
    data: dict[str, str] = Field(default_factory=dict)
    secrets: list[str] = Field(default_factory=list)
    outcomes: dict[str, Outcome]
    assertions: list[Assertion] = Field(default_factory=list, alias="assert")
    max_steps: int = Field(default=20, ge=1, le=60)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    outcome_threshold: float = Field(default=0.8, ge=0.5, le=1.0)
    allowed_hosts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> QaSpec:
        if not self.outcomes:
            raise ValueError("declare at least one outcome")
        if not any(o.verdict == "pass" for o in self.outcomes.values()):
            raise ValueError("declare at least one outcome with verdict 'pass'")
        bad = [n for n in self.outcomes if not NAME.match(n)]
        if bad:
            raise ValueError(f"outcome names must match {NAME.pattern}: {bad}")
        unknown = [s for s in self.secrets if s not in self.data]
        if unknown:
            raise ValueError(f"secrets must name keys of data: {unknown}")
        return self

    @property
    def start_host(self) -> str:
        return re.sub(r"^https?://([^/:?#]+).*$", r"\1", self.start_url).lower()

    @property
    def hosts(self) -> list[str]:
        return [h.lower() for h in self.allowed_hosts] or [self.start_host]

    def preview(self, key: str) -> str:
        """What Jev and the trace see for a data value. Secrets never leave the runner."""
        return "<secret>" if key in self.secrets else self.data[key][:60]

    def secret_values(self) -> list[str]:
        return [self.data[k] for k in self.secrets if self.data[k]]

    def with_env(self, env: Mapping[str, str] | None = None) -> QaSpec:
        """Return a copy with every `${VAR}` / `${VAR:-default}` in `data` resolved from `env`."""
        env = os.environ if env is None else env
        resolved = {key: _resolve(key, value, env) for key, value in self.data.items()}
        return self.model_copy(update={"data": resolved})


def _resolve(key: str, value: str, env: Mapping[str, str]) -> str:
    def sub(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in env:
            return env[name]
        if default is not None:
            return default
        raise SpecError(f"data.{key} needs ${{{name}}} but it is not set in the environment")

    return ENV_REF.sub(sub, value)


def parse_spec(raw: Mapping | str) -> QaSpec:
    """Validate a spec from a dict or a JSON string. Does not touch the environment."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        raise SpecError(f"not valid JSON: {e}") from None
    try:
        return QaSpec.model_validate(data)
    except ValidationError as e:
        lines = [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in e.errors()
        ]
        raise SpecError("invalid spec:\n  " + "\n  ".join(lines)) from None


def load_spec(path: str | Path, env: Mapping[str, str] | None = None) -> QaSpec:
    """Load, validate and resolve `${VAR}` references. Raises SpecError with a readable message."""
    path = Path(path)
    if not path.is_file():
        raise SpecError(f"spec not found: {path}")
    return parse_spec(path.read_text(encoding="utf-8")).with_env(env)
