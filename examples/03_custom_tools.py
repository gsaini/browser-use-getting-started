"""Step 3 — custom tools: let the agent call your Python code.

Decorate a function with `@tools.action(...)`. The description tells the LLM
when to use it; the parameters (names + type hints) become its arguments.
Built-in browser actions stay available alongside yours.

    uv run python examples/03_custom_tools.py
"""

import asyncio
from pathlib import Path

from browser_use import ActionResult, Agent, Tools
from dotenv import load_dotenv

from bu_starter import get_llm

load_dotenv()

BOOKMARKS = Path("output/bookmarks.md")
tools = Tools()


@tools.action(description="Save a page as a bookmark. Call once per page worth keeping.")
def save_bookmark(title: str, url: str) -> ActionResult:
    BOOKMARKS.parent.mkdir(exist_ok=True)
    with BOOKMARKS.open("a", encoding="utf-8") as f:
        f.write(f"- [{title}]({url})\n")
    return ActionResult(extracted_content=f"Saved bookmark: {title}")


async def main() -> None:
    BOOKMARKS.unlink(missing_ok=True)
    agent = Agent(
        task=(
            "On docs.python.org (Python 3 docs), find the asyncio pages titled "
            "'Coroutines and Tasks' and 'Queues', and save each one with save_bookmark."
        ),
        llm=get_llm(),
        tools=tools,
        use_vision=False,
    )
    history = await agent.run(max_steps=20)

    # Don't trust the agent's "done" — check the side effect you asked for.
    saved = BOOKMARKS.read_text(encoding="utf-8") if BOOKMARKS.exists() else ""
    print("\nAgent said:", history.final_result())
    print(f"\n{BOOKMARKS} contains:\n{saved or '(nothing — no bookmark was saved)'}")


if __name__ == "__main__":
    asyncio.run(main())
