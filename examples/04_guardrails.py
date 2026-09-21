"""Step 4 — guardrails: fence the agent in before it touches anything real.

- allowed_domains   the browser refuses to navigate anywhere else
- sensitive_data    the LLM only ever sees placeholders (x_user / x_pass);
                    real values are filled into the page after the LLM call
- use_vision=False  no screenshots, so secrets can't leak through pixels
- max_steps / max_failures   bound cost and retries
- verify the outcome from evidence (the URL actually reached), not the
  agent's own claim of success

Uses the-internet.herokuapp.com, a public practice site whose demo login
(tomsmith / SuperSecretPassword!) is printed on the page itself.

    uv run python examples/04_guardrails.py
"""

import asyncio
import os

from browser_use import Agent, Browser
from dotenv import load_dotenv

from bu_starter import get_llm

load_dotenv()

SITE = "https://the-internet.herokuapp.com"


async def main() -> None:
    browser = Browser(headless=True, allowed_domains=["the-internet.herokuapp.com"])
    agent = Agent(
        task=f"Go to {SITE}/login and log in with username x_user and password x_pass.",
        llm=get_llm(),
        browser=browser,
        # Secrets scoped to one site. The model sees only the placeholder names.
        sensitive_data={
            SITE: {
                "x_user": os.getenv("DEMO_USER", "tomsmith"),
                "x_pass": os.getenv("DEMO_PASS", "SuperSecretPassword!"),
            }
        },
        use_vision=False,
        max_failures=2,
    )
    history = await agent.run(max_steps=10)

    reached_secure_area = any(url and url.startswith(f"{SITE}/secure") for url in history.urls())
    print("\nAgent claims success:", history.is_successful())
    print("Evidence (reached /secure):", reached_secure_area)
    if not reached_secure_area:
        raise SystemExit("Login not verified — don't trust the claim without the evidence.")


if __name__ == "__main__":
    asyncio.run(main())
