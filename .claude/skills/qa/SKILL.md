---
name: qa
description: Goal-driven browser QA for this repo — write a spec (goal, prepared values, declared outcomes with verdicts, code assertions), run it with `uv run jev-qa`, where Jev (TypeSafe's System One decision model) picks every click and keystroke from a numbered element table and Playwright executes, then read result.json and judge PASS / BUG / TEST_ISSUE / NEEDS_HUMAN. Use when the user says "/qa", "QA this flow", "smoke test the login", "write a Jev spec", "test this page with Jev", "reproduce this UI bug as a spec", or asks whether a web flow works. Not for unit tests, API tests, or the browser-use examples (those use a generative LLM on purpose).
allowed-tools: Bash(uv run jev-qa *), Bash(uv run pytest *)
---

# /qa — Jev chooses, Playwright executes, code decides

Claude is the brain, Jev is the hands, Playwright is the body.

- **Claude (you)** writes the *spec* before the run and judges the *result* after it. You never sit
  inside the step loop, so a 30-step flow costs you two turns of thinking, not thirty.
- **Jev** makes one typed decision per step from options the runner offers: which operation, which
  numbered element, which prepared value, plus every declared outcome as a yes/no question, all in
  **one request** (~0.3 s). Jev cannot invent an action that is not on the page and never writes
  text: every string comes from the spec's `data`.
- **Playwright** turns the live page into a numbered element table in one browser call, executes
  the pick, and observes again once the DOM is quiet.

Only a result comes back: `result.json` names exactly **one outcome the spec declared** (with the
verdict attached when it was written and the page line that proves it) or a typed `status` with a
`suggested_verdict`. The runner is deterministic given Jev's answers, so the trace is evidence.

Code lives in `src/jev_qa/` (spec → observe → policy → runner). Specs live in `qa/specs/`, runs in
`qa/runs/<id>/<timestamp>/` (git-ignored).

## 0. Environment (once)

```bash
uv sync && uv run playwright install chromium      # Chromium for Playwright (browser-use has its own)
# .env: TYPESAFE_API_KEY=...  from https://console.typesafe.ai/keys
uv run jev-qa qa/specs/login.json --check           # validates a spec: no browser, no API
```

Never echo the key, never write a credential into a spec: use `${ENV_VAR}` (or `${VAR:-default}`)
in `data` and list the key under `secrets` so traces and Jev see `<secret>`.

## 1. Write the spec — `qa/specs/<id>.json`

| Field | What to write |
|-------|---------------|
| `goal` | What you would tell a tester in one breath, ending with the visible outcome. |
| `data` | Every string the flow might type. Jev chooses *which* value goes *where*; a missing one surfaces as `blocked`. |
| `secrets` | Keys of `data` that must be masked (`<secret>`) in state and traces. |
| `outcomes` | The endings you accept back. The acceptance criteria as `pass`; the wrong behaviour you are testing for (or the ticket reports) as `bug`; a CAPTCHA or approval step as `needs_human`. A negative test declares the rejection as `pass` and the success as `bug`, with a `note`. Write each `when` as **one visible fact per sentence**: that is what gets quoted as evidence. Put `requires_action: true` on a bug that describes "nothing happened", which is also true of the untouched start page. |
| `assert` | Exact checks in code on the final page, free and model-free: `url_matches` (glob), `text_contains`, `element_present`, `element_absent`. Give every spec at least one, so a pass sighting is confirmed at once in code. |
| `max_steps`, `min_confidence`, `outcome_threshold` | Optional. Defaults 20 / 0.6 / 0.8. |

[`qa/specs/login.json`](../../../qa/specs/login.json) and
[`login-wrong-password.json`](../../../qa/specs/login-wrong-password.json) are the templates.
Ask the user only for what you cannot infer (start URL, test account, the app's wording for
success); state your assumptions inline instead of stopping.

## 2. Run

```bash
uv run jev-qa qa/specs/<id>.json             # -> qa/runs/<id>/<ts>/result.json + trace.json + steps/*.png
uv run jev-qa qa/specs/<id>.json --headed    # watch it, when debugging locally
```

Exit 0 = pass; 1 = any other verdict; 2 = never a verdict (spec problem, missing key, Chromium not
installed, start URL did not load). **Fix a 2 first; it is never a bug.**

**Run once, read, then decide.** A rerun that passes tells you nothing about why the first one
failed. Never fire dozens of runs at a shared demo host to answer one question.

## 3. Read the result

The command prints the summary; `result.json` has the same plus `steps`. Read, in order:
`verdict`, `status`, `outcome`, `evidence` (the page's own line), `assertions`, `reason`.

| `status` | Meaning | Start from |
|----------|---------|------------|
| `passed` | a pass outcome was seen and every assertion held | PASS |
| `outcome` | a declared bug / needs_human outcome was seen | that verdict |
| `assert_failed` | pass outcome seen, but an assertion did not hold | BUG, unless the assertion is wrong |
| `done_unverified` | Jev chose DONE; no declared outcome visible after a recheck | TEST_ISSUE (the goal or `when` is unclear) |
| `blocked` | nothing on offer could make progress | TEST_ISSUE (missing `data`, banner, CAPTCHA → NEEDS_HUMAN) |
| `low_confidence` | 3 decisions in a row below `min_confidence`, none executed | TEST_ISSUE (ambiguous page or goal) |
| `stuck` | the same action on the same page 3× | BUG (dead control) or TEST_ISSUE; look at the step screenshot |
| `budget_exhausted` | `max_steps` reached | TEST_ISSUE |
| `off_host` | navigated outside `allowed_hosts` | TEST_ISSUE |
| `error` | browser or API failed mid-run | rerun; not a verdict |

`trace.json` holds every state Jev saw and every answer (probabilities and confidence). Open it
only for a surprising ending. Step *n*'s outcomes describe the page **before** action *n*.

## 4. Judge and report

Exactly one verdict per run: **PASS**, **BUG**, **TEST_ISSUE**, **NEEDS_HUMAN**. A declared outcome
carries its verdict: sanity-check it against `evidence` and the screenshot; if the label does not
fit what you see, the spec mislabelled it (fix `when` or `verdict`, rerun, say so). For an
undetermined status start from `suggested_verdict`. Fix the spec and rerun at most twice before
reporting a test issue. Never call a single run flaky.

Report: verdict · spec id · one sentence of evidence · the run dir · what you changed in the spec, if
anything. For a BUG, add the reproduction: the spec path and the step where it showed.

## Do / Don't

- DO reuse `login.json` as the template; DO give every spec an assertion; DO keep `goal` narrow.
- DO put deterministic preconditions (a known cookie banner, seed data) in the goal *and* an outcome, or ask the user to pre-seed; Jev is for the part a human would have to look at.
- DON'T turn Jev's `DONE` into evidence. DON'T loosen `outcome_threshold` to make a run green.
- DON'T write a secret into a spec, a trace, or this conversation.
- DON'T use this for the browser-use examples (`examples/01–04`, `hn-digest`): they show the generative approach on purpose. Example 05 is the Jev one.
