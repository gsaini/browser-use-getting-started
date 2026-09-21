<div align="center">

# 🌐 Getting Started with browser-use

**Learn [browser-use](https://github.com/browser-use/browser-use) — the open-source Python library that lets an LLM drive a real browser — through a short ladder of runnable examples and one small, verified sample app.**

[![CI](https://github.com/gsaini/browser-use-getting-started/actions/workflows/ci.yml/badge.svg)](https://github.com/gsaini/browser-use-getting-started/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![browser-use](https://img.shields.io/badge/browser--use-0.13.10-FF6B35?style=for-the-badge&logo=googlechrome&logoColor=white)
![Model](https://img.shields.io/badge/Default%20model-Claude%20Opus%205-D97757?style=for-the-badge&logo=anthropic&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=for-the-badge&logo=uv&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-EAB308?style=for-the-badge)

</div>

---

## ✨ What's inside

| | Path | What it teaches |
| - | ---- | --------------- |
| 🧪 | [examples/](examples/) | Five small scripts, each adding **one** idea: setup check → first agent → structured output → custom tools → guardrails. |
| 📰 | [src/hn_digest/](src/hn_digest/) | **HN Digest**, a sample CLI app: an agent reads a Hacker News listing into typed data, and every story is then **checked against the official HN API** before it's written to a Markdown digest. |
| 📖 | [docs/how-it-works.md](docs/how-it-works.md) | The agent loop (observe → decide → act), what drives cost, and the guardrails worth knowing. |
| ✅ | [tests/](tests/) | Offline tests (no browser, no network, no API spend) run in CI. |

## 🧠 browser-use in 30 seconds

You give an `Agent` a task in plain English and an LLM. browser-use opens Chrome, turns the page into a **numbered list of interactive elements**, and asks the LLM what to do next (`click [12]`, `input [4] "zurich"`, `scroll`, `done`…). It runs those actions, looks at the page again, and repeats until the LLM calls `done` or hits your step limit.

```python
from browser_use import Agent, ChatAnthropic

agent = Agent(task="Find the number 1 post on Show HN", llm=ChatAnthropic(model="claude-opus-5"))
history = await agent.run(max_steps=15)
print(history.final_result())
```

More detail in **[docs/how-it-works.md](docs/how-it-works.md)**.

## 🚀 Quickstart

**You need:** Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), Chrome or Chromium, and an API key for one model provider.

```bash
git clone https://github.com/gsaini/browser-use-getting-started.git
cd browser-use-getting-started
uv sync                                     # creates .venv, installs browser-use + this project

uv run python examples/00_check_setup.py    # no API key needed: checks the browser works

cp .env.example .env                        # then add your ANTHROPIC_API_KEY
uv run python examples/01_first_agent.py    # your first agent
```

browser-use uses the Chrome/Chromium already on your machine. If it can't find one, it downloads Chromium through Playwright on first run (or run `uvx playwright install chromium --with-deps` yourself).

<details>
<summary>Without uv (plain pip)</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest ruff          # only for running the tests
python examples/00_check_setup.py
```

</details>

## 🪜 The example ladder

Run them in order; each one adds a single idea to the one before.

| # | Script | New idea | Key API | Costs money? |
| - | ------ | -------- | ------- | :----------: |
| 0 | [00_check_setup.py](examples/00_check_setup.py) | The browser works on your machine | `Browser`, `navigate_to` | No |
| 1 | [01_first_agent.py](examples/01_first_agent.py) | One task in, one answer out; reading the run history | `Agent`, `run(max_steps=…)`, `final_result()` | Yes |
| 2 | [02_structured_output.py](examples/02_structured_output.py) | Get a validated Pydantic object instead of prose | `output_model_schema`, `structured_output` | Yes |
| 3 | [03_custom_tools.py](examples/03_custom_tools.py) | Let the agent call your Python functions, then check their effect | `Tools`, `@tools.action`, `ActionResult` | Yes |
| 4 | [04_guardrails.py](examples/04_guardrails.py) | Domain allowlist, secrets the LLM never sees, and checking the outcome yourself | `allowed_domains`, `sensitive_data`, `use_vision=False` | Yes |

Every example caps its run with `max_steps`, so a confused agent stops instead of running up a bill.

## 📰 The sample app: HN Digest

```bash
uv run hn-digest                                  # front page, top 10
uv run hn-digest --section show --count 5         # Show HN
uv run hn-digest --topic "databases" --count 5    # the LLM filters by meaning, not keywords
uv run hn-digest --section ask --headed           # watch the browser work
```

| Flag | Default | Meaning |
| ---- | ------- | ------- |
| `--section` | `front` | `front`, `new`, `ask`, or `show`. Non-front sections are reached by **clicking** the nav bar, not by typing a URL. |
| `--count` | `10` | Stories to collect (1–30). |
| `--topic` | — | Keep only stories about this topic (scans the first 30). |
| `--max-steps` | `25` | Hard cap on agent steps. |
| `--headed` | off | Show the browser window. |
| `--out` | `digests/` | Where the `.md` and `.json` files go. |

**Output** is a Markdown digest plus a JSON record in `digests/`. The table below shows the format with sample data; your stories, timing and cost will differ:

```markdown
# Hacker News digest — show

> 2026-09-21 09:30 UTC · collected by a browser-use agent (`claude-opus-5`) in 4 steps · 19.8s · 21,400 tokens · **5/5 verified** against the official HN API.

| # | Story | Points | Comments | Check |
|--:|-------|-------:|---------:|:-----:|
| 1 | [Show HN: …](https://…) · [discuss](https://news.ycombinator.com/item?id=…) · by … | 212 | 64 | ✅ |
```

**Exit codes:** `0` every story verified · `1` digest written, but some stories failed verification · `2` no digest (agent failed, or no API key).

### How it's built

```text
src/hn_digest/
├── models.py    Story / Digest — Pydantic models; the agent's `done` must match them
├── agent.py     build_task() + collect(): Browser(allowed_domains) + Agent(output_model_schema)
├── verify.py    looks up every item id in the official HN API and compares title and URL
├── report.py    Markdown + JSON rendering (pure functions, unit-tested)
└── __main__.py  the `hn-digest` command
```

Design choices worth copying:

- **Typed output, not scraping prose.** `output_model_schema=Digest` means the result is validated data. The field descriptions in [models.py](src/hn_digest/models.py) are the extraction instructions.
- **Trust, then verify.** An agent that says `done` has made a claim. [verify.py](src/hn_digest/verify.py) checks every story against the [official Hacker News API](https://github.com/HackerNews/API) and flags invented or garbled entries. Scores keep moving, so a score difference is reported as a note, not a failure.
- **Fenced in.** `allowed_domains=["news.ycombinator.com"]`, the prompt says no logging in or voting, `max_steps` bounds cost, and `use_vision=False` keeps the text-only listing cheap.
- **Honest about the demo.** In production you'd call the HN API directly. HN is used here because it's public, stable, bot-friendly, and has an official API to grade the agent against. The same approach works for sites that don't.

## 🤖 Choosing a model

All examples and the app get their model from [src/bu_starter/llm.py](src/bu_starter/llm.py), configured in `.env`:

| `.env` | Model |
| ------ | ----- |
| `ANTHROPIC_API_KEY=…` *(default)* | **Claude Opus 5** (`claude-opus-5`). If Opus 5 declines a request, the API retries it on `claude-opus-4-8` (server-side fallback). |
| `+ ANTHROPIC_MODEL=claude-sonnet-5` | Any Claude model ID, e.g. `claude-sonnet-5` or `claude-haiku-4-5`, which cost less per step. |
| `LLM_PROVIDER=browser-use` + `BROWSER_USE_API_KEY=…` | Browser Use's own **BU2** model (`bu-2-0`), tuned for browser tasks. |

browser-use also supports OpenAI, Gemini, Groq, Ollama (local) and more. To use one, add its `Chat*` class in `llm.py`; nothing else changes. Compare models by **cost per completed task**: a cheaper model that needs more steps or retries isn't actually cheaper.

## 🛡️ Safety notes

- An agent acts **with your browser**. Keep it on a fresh profile (the default), not your logged-in one, unless you mean to.
- Page text is **untrusted input** and can try to steer the agent (prompt injection). Use `allowed_domains`, avoid stored logins, and check outcomes independently.
- Pass credentials through `sensitive_data` so the LLM only sees placeholders ([example 04](examples/04_guardrails.py)).
- Respect each site's terms and rate limits. Don't automate anything you wouldn't do by hand.
- browser-use sends anonymous telemetry unless you set `ANONYMIZED_TELEMETRY=false`, which `.env.example` does.

## 🧰 Development

```bash
uv run pytest -q          # offline: no browser, no network, no API spend
uv run ruff check . && uv run ruff format --check .
```

CI runs the same commands on every push.

## 🩺 Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `LLM_PROVIDER=anthropic needs ANTHROPIC_API_KEY` | `cp .env.example .env` and add your key. |
| Step 0 can't start a browser | Install Chrome, or run `uvx playwright install chromium --with-deps`. On Linux servers keep `headless=True`. |
| Agent stops at the step limit | Make the task more specific, or raise `max_steps` / `--max-steps` a little. |
| A site shows a CAPTCHA or blocks the agent | Expected on some sites. Try a different site, or look at [Browser Use Cloud](https://docs.browser-use.com/cloud/browser/quickstart) stealth browsers. |
| HN Digest exits with code `1` | Read the "Verification notes" in the digest: the agent misread or invented a story. That's the check doing its job. |

## 📚 Learn more

- [browser-use docs](https://docs.browser-use.com/open-source/introduction) · [all Agent parameters](https://docs.browser-use.com/open-source/customize/agent/all-parameters) · [all Browser parameters](https://docs.browser-use.com/open-source/customize/browser/all-parameters) · [official examples](https://github.com/browser-use/browser-use/tree/main/examples)
- [Jev Ultrafast study note](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/jev-ultrafast.md): a different design from the Browser Use team, where the model **chooses** an indexed action instead of generating one.
- [Building an Agent Evaluator](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/building-agent-evaluators.md): why `done` is a claim and how to grade it.

## 📜 License

[MIT](LICENSE). browser-use is MIT-licensed by its authors. This is an independent learning project, not affiliated with Browser Use or Anthropic.
