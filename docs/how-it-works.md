# How a browser-use agent works

A browser-use agent is a loop around a real Chrome browser. Every **step** has the same four parts:

```text
        ┌─────────────────────────────────────────────────────────────┐
        │                                                             │
        ▼                                                             │
 1. OBSERVE           2. DECIDE (1 LLM call)      3. ACT              │
 page → indexed   →   thinking, memory,       →   browser-use runs    │
 element list         next_goal + actions         the actions via CDP ┘
 (+ screenshot)       e.g. click(12), input(…)        │
                                                       ▼
                                          4. STOP when the LLM calls `done`
                                             or max_steps / max_failures is hit
```

## 1. Observe: the page becomes a numbered list

browser-use drives Chrome over the Chrome DevTools Protocol (CDP). Each step it reads the DOM and gives every **interactive element an index**, so the model sees something like:

```text
[12]<a>show</a>
[31]<a>Show HN: A tiny SQLite browser</a>
[32]<a>57 comments</a>
```

With `use_vision=True` (the default) a screenshot goes along with it. With `use_vision=False` the model gets text only — cheaper and faster, and enough for text-heavy pages like Hacker News or Wikipedia. The examples and the app use text-only mode wherever it's enough.

## 2. Decide: one structured LLM call per step

The model returns an `AgentOutput`: its `thinking`, an `evaluation_previous_goal` (did the last step work?), running `memory`, a `next_goal`, and a list of **actions** — up to `max_actions_per_step` (default 5) — that refer to elements **by index**.

## 3. Act: built-in tools + yours

Built-in actions include `navigate`, `search`, `click`, `input`, `scroll`, `send_keys`, `select_dropdown`, `extract`, `find_text`, `screenshot`, `go_back`, `switch`/`close` tabs, file actions (`write_file`, `read_file`), and `done`. Your own `@tools.action` functions ([example 03](../examples/03_custom_tools.py)) sit right next to them. After the page changes, remaining actions in the batch are skipped and the loop observes again.

## 4. Stop and inspect the history

`agent.run(max_steps=…)` returns an `AgentHistoryList`:

| Call | What you get |
| ---- | ------------ |
| `final_result()` | the text the agent passed to `done` |
| `structured_output` | that result parsed into your `output_model_schema` |
| `is_done()` / `is_successful()` | whether it called `done`, and **its own** success claim |
| `urls()`, `action_names()`, `errors()` | what actually happened, step by step |
| `number_of_steps()`, `total_duration_seconds()`, `usage` | cost and speed |

> `is_successful()` is the agent grading itself. For anything that matters, check the outcome another way — the URL you actually reached ([example 04](../examples/04_guardrails.py)), the file you asked it to write ([example 03](../examples/03_custom_tools.py)), or an independent source of truth ([the HN Digest app](../src/hn_digest/verify.py)).

## What drives cost and speed

- **Steps × page size.** Each step is one LLM call carrying the current page state. Fewer steps and smaller pages mean lower cost. Always pass `max_steps`; `run()` defaults to 500.
- **Vision.** Screenshots add tokens. Turn them off when text is enough.
- **Task wording.** A precise task ("open X, read the first 10 rows, don't open links") finishes in far fewer steps than a vague one.
- **Model.** Bigger models make fewer mistakes per step; smaller ones are cheaper per step. Compare cost per *completed task*, not per call.

## Guardrails worth knowing

| Setting | What it does |
| ------- | ------------ |
| `Browser(allowed_domains=[...])` | Navigation outside the list is blocked. |
| `sensitive_data={...}` | The LLM sees placeholder names; real values are typed into the page after the LLM call. |
| `use_vision=False` | No screenshots, so secrets on screen can't reach the model through pixels. |
| `max_steps`, `max_failures` | Hard limits on cost and retries. |
| `extend_system_message` | Adds house rules to browser-use's built-in system prompt. |

Page content is **untrusted input**: a page can contain text that tries to steer the agent (prompt injection). Domain allowlists, no stored logins, and checking the outcome independently are what keep a misled agent from doing damage.
