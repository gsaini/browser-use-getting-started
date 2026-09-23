"""jev_qa: a QA runner where Jev chooses, Playwright executes, and code decides.

Jev is TypeSafe's "System One" decision model, the one behind Browser Use's jev-ultrafast.
It never generates text: each step it picks an operation and an element index from menus
the code built. Playwright executes the pick; the spec's declared outcomes and assertions
decide the verdict. See README.md ("The QA runner") and .claude/skills/qa/SKILL.md.
"""

from jev_qa.report import render
from jev_qa.runner import RunnerUnavailable, RunResult, run
from jev_qa.spec import QaSpec, SpecError, load_spec, parse_spec

__all__ = [
    "QaSpec",
    "RunResult",
    "RunnerUnavailable",
    "SpecError",
    "load_spec",
    "parse_spec",
    "render",
    "run",
]
