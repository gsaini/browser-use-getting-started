"""Ask a browser-use agent to read a Hacker News listing into a Digest."""

from __future__ import annotations

from dataclasses import dataclass

from browser_use import Agent, AgentHistoryList, Browser

from bu_starter import get_llm
from hn_digest.models import Digest

HN = "https://news.ycombinator.com"

# section -> link text in HN's top navigation bar (the front page needs no click)
SECTIONS: dict[str, str | None] = {"front": None, "new": "new", "ask": "ask", "show": "show"}


@dataclass
class RunResult:
    digest: Digest | None
    history: AgentHistoryList
    model: str


def build_task(section: str, count: int, topic: str | None = None) -> str:
    """The instructions the agent gets. Kept pure so it can be unit-tested."""
    link = SECTIONS[section]
    nav = f"Open {HN}."
    if link is not None:
        nav = f"Open {HN} and click '{link}' in the top navigation bar."
    if topic:
        scope = (
            f"Scan the first 30 stories and keep only those clearly about {topic!r}, "
            f"up to {count}. Returning fewer than {count} (even none) is fine."
        )
    else:
        scope = f"Read the first {count} stories."
    return (
        f"{nav} {scope}\n"
        "For each story record: rank, title, link URL, points, comment count, author, "
        "and item id (the number in its 'item?id=' comments link).\n"
        "Copy values exactly as shown on the page. Never guess: use null for anything "
        "not shown. Do not open the stories themselves, and do not log in or vote."
    )


async def collect(
    section: str = "front",
    count: int = 10,
    topic: str | None = None,
    *,
    headless: bool = True,
    max_steps: int = 25,
) -> RunResult:
    browser = Browser(
        headless=headless,
        allowed_domains=["news.ycombinator.com"],  # the agent can't wander off HN
    )
    llm = get_llm()
    agent = Agent(
        task=build_task(section, count, topic),
        llm=llm,
        browser=browser,
        output_model_schema=Digest,
        use_vision=False,  # the listing is plain text; screenshots would only add cost
        max_failures=3,
        calculate_cost=True,
    )
    history = await agent.run(max_steps=max_steps)
    return RunResult(digest=history.structured_output, history=history, model=str(llm.model))
