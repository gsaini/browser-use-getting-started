"""Step 2 — structured output: get a validated Pydantic object, not prose.

Pass `output_model_schema`; the agent's final `done` action must match it, and
`history.structured_output` parses it for you. The field descriptions are part
of the prompt — write them as instructions.

    uv run python examples/02_structured_output.py
"""

import asyncio

from browser_use import Agent
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from bu_starter import get_llm

load_dotenv()


class LanguageFacts(BaseModel):
    name: str
    first_appeared: int = Field(description="Year the language first appeared")
    designed_by: list[str] = Field(description="Designer(s) as listed in the infobox")
    latest_stable_release: str = Field(description="Version string exactly as shown")
    source_url: str = Field(description="The page the facts were read from")


async def main() -> None:
    agent = Agent(
        task=(
            "Open the English Wikipedia article for the Python programming language "
            "and read the facts from its infobox."
        ),
        llm=get_llm(),
        output_model_schema=LanguageFacts,
        use_vision=False,  # text-only page state: cheaper, and enough for reading an infobox
    )
    history = await agent.run(max_steps=10)

    facts = history.structured_output  # a LanguageFacts instance, or None if the run failed
    if facts is None:
        raise SystemExit(f"No structured result. Errors: {[e for e in history.errors() if e]}")
    print(facts.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
