"""The loop: observe -> ask Jev -> validate -> execute -> settle, until a declared ending is seen.

No language model sits in this loop. The spec was written beforehand (by you, or by Claude
through the `/qa` skill); Jev makes one typed decision per step; Playwright executes; the
spec's `assert` block is checked in code. Everything here is deterministic given Jev's
answers, which is what makes the trace usable as evidence.

A run ends in exactly one of:

    passed           a pass outcome was seen and every assertion held
    outcome          a declared outcome with verdict bug / needs_human was seen
    assert_failed    a pass outcome was seen but an assertion did not hold
    done_unverified  Jev chose DONE, and after a settle-and-recheck no pass outcome is visible
    blocked          Jev chose BLOCKED: nothing on offer could make progress
    off_host         the page navigated outside the spec's allowed hosts
    low_confidence   three consecutive decisions below min_confidence (none executed)
    stuck            the same action on the same page three times in a row
    budget_exhausted max_steps reached
    error            the browser or the TypeSafe API failed mid-run
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, SystemOneResponse, TypeSafeError

from jev_qa.observe import Observation, mask, observe
from jev_qa.policy import (
    Decision,
    PolicyError,
    build_questions,
    build_state,
    evidence_line,
    outcome_questions,
    read_decision,
    read_outcomes,
)
from jev_qa.spec import Assertion, QaSpec

Ask = Callable[[dict, Mapping[str, Any]], Awaitable[SystemOneResponse]]
Status = Literal[
    "passed",
    "outcome",
    "assert_failed",
    "done_unverified",
    "blocked",
    "off_host",
    "low_confidence",
    "stuck",
    "budget_exhausted",
    "error",
]
Screenshots = Literal["key", "all", "none"]

ACTION_TIMEOUT_MS = 5_000
NAVIGATION_TIMEOUT_MS = 20_000
MAX_LOW_CONFIDENCE = 3
MAX_REPEAT = 3
MAX_BAD_ANSWERS = 2

SUGGESTED_VERDICT = {
    "assert_failed": "bug",
    "done_unverified": "test_issue",
    "blocked": "test_issue",
    "off_host": "test_issue",
    "low_confidence": "test_issue",
    "stuck": "bug",
    "budget_exhausted": "test_issue",
    "error": None,
}


class RunnerUnavailable(RuntimeError):
    """Browser, start page or API key unavailable: an environment problem, never a verdict."""


class StepRecord(BaseModel):
    n: int
    url: str
    title: str = ""
    elements: int = 0
    operation: str = ""
    target: str | None = None
    value_key: str | None = None
    confidence: float = 0.0
    outcomes: dict[str, float] = Field(default_factory=dict)
    executed: bool = False
    note: str = ""
    jev_ms: int = 0
    screenshot: str | None = None


class AssertionResult(BaseModel):
    check: str
    ok: bool
    detail: str = ""


class RunResult(BaseModel):
    spec_id: str
    status: Status
    verdict: Literal["pass", "bug", "needs_human", "undetermined"]
    suggested_verdict: str | None = None
    outcome: str | None = None
    evidence: str = ""
    reason: str = ""
    final_url: str = ""
    assertions: list[AssertionResult] = Field(default_factory=list)
    steps: list[StepRecord] = Field(default_factory=list)
    jev_requests: int = 0
    jev_input_tokens: int = 0
    model: str = ""
    started_at: str = ""
    duration_ms: int = 0
    out_dir: str | None = None

    @property
    def exit_code(self) -> int:
        """0 = pass, 1 = any other verdict, 2 = never a verdict (the run itself failed)."""
        if self.status == "error":
            return 2
        return 0 if self.verdict == "pass" else 1


SETTLE_JS = r"""
(args) => new Promise(resolve => {
  const { quietMs, capMs } = args;
  const t0 = performance.now();
  let last = t0, frames = 0, done = false;
  const mo = new MutationObserver(() => { last = performance.now(); });
  const all = { subtree: true, childList: true, attributes: true, characterData: true };
  try { mo.observe(document.documentElement, all); } catch (e) {}
  const finish = how => {
    if (done) return;
    done = true; mo.disconnect();
    resolve({ ended: how, ms: Math.round(performance.now() - t0) });
  };
  const cap = setTimeout(() => finish('cap'), capMs);
  const tick = () => {
    if (done) return;
    frames++;
    if (frames >= 2 && performance.now() - last >= quietMs) {
      clearTimeout(cap); return finish('quiet');
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})
"""

BODY_TEXT_JS = "() => document.body ? document.body.innerText : ''"


async def settle(page: Any, *, quiet_ms: int = 150, cap_ms: int = 1500) -> dict:
    """Wait until the DOM has been quiet for `quiet_ms` (two frames minimum), capped at `cap_ms`."""

    async def loaded() -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=cap_ms)
        except Exception:  # noqa: BLE001 - a slow page is not an error here
            pass

    await loaded()
    for attempt in range(2):
        try:
            return await page.evaluate(SETTLE_JS, {"quietMs": quiet_ms, "capMs": cap_ms})
        except Exception:  # noqa: BLE001 - the document navigated while we waited
            if attempt == 0:
                await loaded()
    await page.wait_for_timeout(quiet_ms)
    return {"ended": "navigated", "ms": quiet_ms}


def check_text_assertion(a: Assertion, url: str, text: str) -> tuple[bool, str]:
    """The model-free checks that need only the URL and the visible text (pure, unit-tested)."""
    if a.kind == "url_matches":
        bare = url.split("#")[0].split("?")[0].rstrip("/")
        return fnmatch(url, a.arg) or fnmatch(bare, a.arg), f"url is {url}"
    if a.kind == "text_contains":
        norm = " ".join(text.split()).lower()
        found = " ".join(a.arg.split()).lower() in norm
        return found, "found in page text" if found else "not in page text"
    raise ValueError(a.kind)


async def check_assertions(page: Any, spec: QaSpec) -> list[AssertionResult]:
    url = page.url
    text = await page.evaluate(BODY_TEXT_JS)
    results = []
    for a in spec.assertions:
        if a.kind in {"url_matches", "text_contains"}:
            ok, detail = check_text_assertion(a, url, text)
        else:
            n = await page.locator(a.arg).count()
            ok = n > 0 if a.kind == "element_present" else n == 0
            detail = f"{n} match(es)"
        results.append(AssertionResult(check=a.describe(), ok=ok, detail=detail))
    return results


def on_allowed_host(url: str, hosts: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return True  # about:blank and friends
    return any(host == h or host.endswith("." + h) for h in hosts)


async def execute(page: Any, decision: Decision, spec: QaSpec) -> None:
    op = decision.operation
    if op in {"CLICK", "TYPE_TEXT"}:
        locator = page.locator(f'[data-jev-idx="{decision.target}"]').first
        if op == "CLICK":
            await locator.click(timeout=ACTION_TIMEOUT_MS)
        else:
            await locator.fill(spec.data[decision.value_key or ""], timeout=ACTION_TIMEOUT_MS)
    elif op == "PRESS_ENTER":
        await page.keyboard.press("Enter")
    elif op == "SCROLL_DOWN":
        await page.mouse.wheel(0, 600)
    elif op == "SCROLL_UP":
        await page.mouse.wheel(0, -600)
    elif op == "WAIT":
        await page.wait_for_timeout(700)


def default_ask(model: str | None) -> tuple[AsyncTypeSafeClient, Ask]:
    try:
        client = AsyncTypeSafeClient(
            model=model or os.environ.get("TYPESAFE_MODEL", "jev-latest"),
            retry=RetryPolicy(max_retries=2),
        )
    except (TypeSafeError, ValueError) as e:
        raise RunnerUnavailable(
            f"TypeSafe client could not start ({e}). Set TYPESAFE_API_KEY in your .env "
            "(get a key at https://console.typesafe.ai/keys)."
        ) from None

    async def ask(state: dict, questions: Mapping[str, Any]) -> SystemOneResponse:
        return await client.system_one(state=state, questions=questions)

    return client, ask


class _Run:
    """One run's mutable state; `run()` is the public entry point."""

    def __init__(self, spec: QaSpec, out_dir: Path | None, screenshots: Screenshots) -> None:
        self.spec = spec
        self.out_dir = out_dir
        self.screenshots = screenshots
        self.steps: list[StepRecord] = []
        self.history: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self.requests = 0
        self.input_tokens = 0
        self.model = ""
        self.secrets = spec.secret_values()

    def note_response(self, response: SystemOneResponse) -> None:
        self.requests += 1
        self.model = response.model or self.model
        if response.usage:
            self.input_tokens += response.usage.input_tokens or 0

    async def snapshot(self, page: Any, n: int, *, key: bool) -> str | None:
        if (
            self.out_dir is None
            or self.screenshots == "none"
            or (self.screenshots == "key" and not key)
        ):
            return None
        path = self.out_dir / "steps" / f"{n:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(path), timeout=3000)
        except Exception:  # noqa: BLE001 - a missing picture must not fail a run
            return None
        return str(path.relative_to(self.out_dir))

    def finish(
        self,
        status: Status,
        *,
        started: float,
        started_at: str,
        outcome: str | None = None,
        evidence: str = "",
        reason: str = "",
        assertions: list[AssertionResult] | None = None,
        final_url: str = "",
    ) -> RunResult:
        if status == "passed":
            verdict: str = "pass"
        elif status == "outcome" and outcome:
            verdict = self.spec.outcomes[outcome].verdict
        else:
            verdict = "undetermined"
        result = RunResult(
            spec_id=self.spec.id,
            status=status,
            verdict=verdict,  # type: ignore[arg-type]
            suggested_verdict=None if verdict != "undetermined" else SUGGESTED_VERDICT.get(status),
            outcome=outcome,
            evidence=mask(evidence, self.secrets),
            reason=reason,
            final_url=final_url,
            assertions=assertions or [],
            steps=self.steps,
            jev_requests=self.requests,
            jev_input_tokens=self.input_tokens,
            model=self.model,
            started_at=started_at,
            duration_ms=int((time.perf_counter() - started) * 1000),
            out_dir=str(self.out_dir) if self.out_dir else None,
        )
        if self.out_dir is not None:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "result.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            redacted = self.spec.model_dump(by_alias=True)
            redacted["data"] = {k: self.spec.preview(k) for k in self.spec.data}
            trace = {"spec": redacted, "steps": self.trace}
            (self.out_dir / "trace.json").write_text(
                mask(json.dumps(trace, indent=2, default=str), self.secrets), encoding="utf-8"
            )
        return result


async def run(
    spec: QaSpec,
    *,
    headed: bool = False,
    out_dir: str | Path | None = None,
    screenshots: Screenshots = "key",
    ask: Ask | None = None,
    model: str | None = None,
) -> RunResult:
    """Run one spec to a result. Tests replace `ask` with a scripted fake instead of the API."""
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    started, started_at = time.perf_counter(), datetime.now(UTC).isoformat(timespec="seconds")
    run_dir = Path(out_dir) / spec.id / started_at.replace(":", "-") if out_dir else None
    state = _Run(spec, run_dir, screenshots)
    client: AsyncTypeSafeClient | None = None
    if ask is None:
        client, ask = default_ask(model)

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=not headed)
        except PlaywrightError as e:
            raise RunnerUnavailable(
                f"Chromium did not launch ({str(e).splitlines()[0]}). "
                "Run: uv run playwright install chromium"
            ) from None
        try:
            page = await (
                await browser.new_context(viewport={"width": 1280, "height": 900})
            ).new_page()
            try:
                await page.goto(
                    spec.start_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS
                )
            except PlaywrightError as e:
                raise RunnerUnavailable(
                    f"start URL did not load: {str(e).splitlines()[0]}"
                ) from None
            await settle(page)
            return await _loop(page, spec, state, ask, started, started_at)
        finally:
            await browser.close()
            if client is not None:
                await client.__aexit__(None, None, None)


async def _loop(
    page: Any, spec: QaSpec, st: _Run, ask: Ask, started: float, started_at: str
) -> RunResult:
    low_streak = bad_streak = repeat = 0
    last_signature: tuple | None = None
    typed_before = False

    def done(status: Status, **kw: Any) -> RunResult:
        return st.finish(status, started=started, started_at=started_at, final_url=page.url, **kw)

    async def confirm_pass(obs: Observation, name: str) -> RunResult:
        results = await check_assertions(page, spec)
        evidence = evidence_line(obs.text, spec.outcomes[name].when)
        if all(r.ok for r in results):
            return done("passed", outcome=name, evidence=evidence, assertions=results)
        failed = ", ".join(r.check for r in results if not r.ok)
        return done(
            "assert_failed",
            outcome=name,
            evidence=evidence,
            assertions=results,
            reason=f"pass outcome {name!r} seen, but did not hold: {failed}",
        )

    for n in range(1, spec.max_steps + 1):
        if not on_allowed_host(page.url, spec.hosts):
            return done(
                "off_host", reason=f"navigated to {page.url}, outside allowed hosts {spec.hosts}"
            )
        obs = await observe(page)
        obs = obs.model_copy(update={"text": mask(obs.text, st.secrets)})
        state = build_state(spec, obs, st.history, n)
        questions, offered = build_questions(spec, obs, typed_before=typed_before)
        rec = StepRecord(n=n, url=obs.url, title=obs.title, elements=len(obs.elements))
        st.steps.append(rec)
        t0 = time.perf_counter()
        try:
            response = await ask(state, questions)
        except TypeSafeError as e:
            rec.note = f"TypeSafe API error: {e}"
            return done("error", reason=rec.note)
        rec.jev_ms = int((time.perf_counter() - t0) * 1000)
        st.note_response(response)
        answers = response.answers
        st.trace.append(
            {
                "n": n,
                "state": state,
                "offered": offered.__dict__,
                "answers": {k: v.model_dump() for k, v in answers.items()},
                "jev_ms": rec.jev_ms,
            }
        )

        try:
            decision = read_decision(answers, offered, spec)
        except PolicyError as e:
            bad_streak += 1
            rec.note = f"answer rejected: {e}"
            rec.screenshot = await st.snapshot(page, n, key=True)
            if bad_streak >= MAX_BAD_ANSWERS:
                return done(
                    "error",
                    reason=f"{MAX_BAD_ANSWERS} consecutive answers did not fit the offered options",
                )
            continue
        bad_streak = 0
        rec.operation, rec.confidence, rec.outcomes = (
            decision.operation,
            decision.confidence,
            decision.outcomes,
        )
        rec.value_key = decision.value_key
        if decision.target is not None:
            rec.target = obs.element(decision.target).describe()["element"]

        acted = any(s.executed for s in st.steps)
        seen = decision.seen_outcome(spec, acted=acted)
        if seen is not None:
            rec.note = f"outcome {seen} seen ({decision.outcomes[seen]:.2f})"
            rec.screenshot = await st.snapshot(page, n, key=True)
            if spec.outcomes[seen].verdict == "pass":
                return await confirm_pass(obs, seen)
            return done(
                "outcome",
                outcome=seen,
                evidence=evidence_line(obs.text, spec.outcomes[seen].when),
                assertions=await check_assertions(page, spec),
            )

        if decision.operation == "DONE":
            rec.note = "DONE claimed; settle and recheck"
            await settle(page, cap_ms=2500)
            recheck = await observe(page)
            response = await ask(build_state(spec, recheck, st.history, n), outcome_questions(spec))
            st.note_response(response)
            outcomes = read_outcomes(response.answers, spec)
            rec.outcomes = outcomes
            rec.screenshot = await st.snapshot(page, n, key=True)
            best = max(outcomes, key=outcomes.get, default=None)
            if best is not None and outcomes[best] >= spec.outcome_threshold:
                if spec.outcomes[best].verdict == "pass":
                    return await confirm_pass(recheck, best)
                return done(
                    "outcome",
                    outcome=best,
                    evidence=evidence_line(recheck.text, spec.outcomes[best].when),
                )
            return done(
                "done_unverified",
                reason="Jev chose DONE but no declared outcome is visible after a recheck",
            )

        if decision.operation == "BLOCKED":
            rec.screenshot = await st.snapshot(page, n, key=True)
            return done(
                "blocked", reason="Jev chose BLOCKED: no offered operation could make progress"
            )

        if decision.low_confidence(spec):
            low_streak += 1
            rec.note = f"low confidence, not executed ({low_streak}/{MAX_LOW_CONFIDENCE})"
            rec.screenshot = await st.snapshot(page, n, key=True)
            if low_streak >= MAX_LOW_CONFIDENCE:
                return done(
                    "low_confidence", reason="Jev could not choose between the offered options"
                )
            await page.wait_for_timeout(500)
            continue
        low_streak = 0

        signature = (decision.operation, rec.target, decision.value_key, obs.url, obs.title)
        repeat = repeat + 1 if signature == last_signature else 1
        last_signature = signature
        if repeat >= MAX_REPEAT:
            rec.screenshot = await st.snapshot(page, n, key=True)
            return done(
                "stuck", reason=f"{decision.summary()} repeated {MAX_REPEAT} times on the same page"
            )

        try:
            await execute(page, decision, spec)
        except Exception as e:  # noqa: BLE001 - a failed click is data, not a crash
            rec.note = f"action failed: {str(e).splitlines()[0][:160]}"
        else:
            rec.executed = True
            typed_before = typed_before or decision.operation == "TYPE_TEXT"
        st.history.append(
            {
                "action": decision.summary(),
                "target": rec.target,
                "executed": rec.executed,
                "url": obs.url,
            }
        )
        rec.screenshot = await st.snapshot(page, n, key=False)
        await settle(page)

    st.steps[-1].screenshot = await st.snapshot(page, len(st.steps), key=True)
    return done(
        "budget_exhausted", reason=f"max_steps={spec.max_steps} reached without a declared outcome"
    )
