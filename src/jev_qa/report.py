"""Render a run result for the terminal (pure functions, unit-tested)."""

from __future__ import annotations

from jev_qa.runner import RunResult

MARK = {True: "ok ", False: "FAIL"}


def render(result: RunResult) -> str:
    verdict = result.verdict.upper()
    if result.verdict == "undetermined" and result.suggested_verdict:
        verdict += f" (suggested: {result.suggested_verdict})"
    head = (
        f"{result.spec_id} · {verdict} · status {result.status}"
        + (f" · outcome {result.outcome}" if result.outcome else "")
        + f" · {len(result.steps)} steps · {result.jev_requests} Jev requests"
        + f" · {result.duration_ms / 1000:.1f}s"
    )
    lines = [head]
    if result.reason:
        lines.append(f"  reason: {result.reason}")
    if result.evidence:
        lines.append(f'  evidence: "{result.evidence}"')
    for a in result.assertions:
        lines.append(f"  assert {MARK[a.ok]} {a.check} ({a.detail})")
    for s in result.steps:
        target = f" -> {s.target}" if s.target else ""
        value = f" value={s.value_key}" if s.value_key else ""
        flag = "" if s.executed else "   (not executed)"
        note = f"  · {s.note}" if s.note else ""
        lines.append(
            f"  {s.n:>2}. {s.operation or '-'} ({s.confidence:.2f}){target}{value}{flag}{note}"
        )
    if result.model:
        lines.append(f"  model {result.model} · {result.jev_input_tokens} input tokens")
    if result.out_dir:
        lines.append(f"  run dir: {result.out_dir}")
    return "\n".join(lines)
