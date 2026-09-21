"""Step 1 — your first agent: one plain-English task, one answer.

The agent loop, in one sentence: read the page -> the LLM picks actions
(click element [7], type, scroll, open URL, ...) -> browser-use executes them
-> repeat until the LLM calls `done` or runs out of steps.

    uv run python examples/01_first_agent.py
"""

import asyncio

from browser_use import Agent
from dotenv import load_dotenv

from bu_starter import get_llm

load_dotenv()


async def main() -> None:
    agent = Agent(
        task="Find the number 1 post on Show HN and tell me its title and points.",
        llm=get_llm(),
    )
    # Always cap the loop. run()'s default is 500 steps — far too many to pay for.
    history = await agent.run(max_steps=15)

    print("\nAnswer:   ", history.final_result())
    print("Done?     ", history.is_done(), "| agent says success:", history.is_successful())
    print("Steps:    ", history.number_of_steps(), f"in {history.total_duration_seconds():.1f}s")
    print("Visited:  ", history.urls())


if __name__ == "__main__":
    asyncio.run(main())
