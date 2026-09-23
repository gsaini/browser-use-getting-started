"""Step 5 — the other way round: choose, don't generate (Jev + Playwright).

Examples 1–4 ask a language model to *generate* the next action. This one asks Jev,
TypeSafe's "System One" decision model (the one behind Browser Use's jev-ultrafast), to
*choose* it. Every step the runner turns the page into a numbered menu, Jev picks an
operation and an index in one ~0.3 s request, Playwright executes the pick, and code
decides the verdict from the outcomes and assertions declared up front. Nothing is ever
generated: the only strings the runner can type are the ones in `data`.

Needs TYPESAFE_API_KEY in .env (https://console.typesafe.ai/keys). No Anthropic key.

    uv run python examples/05_jev_chooses.py
    uv run python examples/05_jev_chooses.py --headed
"""

import asyncio
import sys

from dotenv import load_dotenv

from jev_qa import QaSpec, RunnerUnavailable, render, run

load_dotenv()

SITE = "https://the-internet.herokuapp.com"

# The same contract the `/qa` skill writes as JSON in qa/specs/. Outcomes are the endings
# you accept back, each with the verdict you attach *before* the run; `assert` is checked in code.
SPEC = QaSpec.model_validate(
    {
        "id": "login-example",
        "start_url": f"{SITE}/login",
        "goal": "Log in with the prepared username and password. "
        "Done when the secure area is shown.",
        "data": {"username": "tomsmith", "password": "SuperSecretPassword!"},  # printed on the page
        "outcomes": {
            "logged_in": {"when": "The page heading says 'Secure Area'.", "verdict": "pass"},
            "rejected": {
                "when": "A flash message says the username or password is invalid.",
                "verdict": "bug",
            },
        },
        "assert": [
            {"url_matches": "**/secure"},
            {"text_contains": "You logged into a secure area!"},
        ],
    }
)


async def main(headed: bool) -> None:
    try:
        result = await run(SPEC, headed=headed, out_dir="qa/runs")
    except RunnerUnavailable as e:  # never a verdict: exit 2, like `jev-qa`
        print(f"could not run: {e}", file=sys.stderr)
        raise SystemExit(2) from None

    print(render(result))
    # As in example 04: a claim of success is not evidence. The verdict comes from the
    # declared outcome Jev saw on the page *and* the assertions that held in code.
    if result.verdict != "pass":
        raise SystemExit(result.exit_code)


if __name__ == "__main__":
    asyncio.run(main("--headed" in sys.argv))
