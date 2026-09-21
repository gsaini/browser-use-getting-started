"""Check the agent's answer against the official Hacker News API.

The agent saying `done` is a claim, not evidence. Every story it returns is
looked up by item id at https://github.com/HackerNews/API and compared.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx

from hn_digest.models import Digest, Story

ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

Status = Literal["verified", "mismatch", "missing_id", "not_found", "error"]


@dataclass(frozen=True)
class Check:
    story: Story
    status: Status
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "verified"


def _norm(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def _norm_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def compare(story: Story, item: dict | None) -> Check:
    """Pure comparison of one extracted story with its API record."""
    if story.item_id is None:
        return Check(story, "missing_id", "agent did not capture an item id")
    if not item:
        return Check(story, "not_found", f"no item {story.item_id} in the API")

    problems = []
    if _norm(story.title) != _norm(item.get("title")):
        problems.append(f"title: page {story.title!r} vs API {item.get('title')!r}")
    api_url = item.get("url")
    if story.url and api_url and _norm_url(story.url) != _norm_url(api_url):
        problems.append(f"url: page {story.url!r} vs API {api_url!r}")
    if problems:
        return Check(story, "mismatch", "; ".join(problems))

    # Scores keep moving, so a difference is information, not a failure.
    score = item.get("score")
    drift = ""
    if story.points is not None and score is not None and score != story.points:
        drift = f"score now {score} (page showed {story.points})"
    return Check(story, "verified", drift)


async def _fetch(client: httpx.AsyncClient, item_id: int) -> dict | None:
    response = await client.get(ITEM_URL.format(id=item_id))
    response.raise_for_status()
    return response.json()  # the API returns JSON null for unknown ids


async def verify(digest: Digest, client: httpx.AsyncClient | None = None) -> list[Check]:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:

        async def check(story: Story) -> Check:
            if story.item_id is None:
                return compare(story, None)
            try:
                return compare(story, await _fetch(client, story.item_id))
            except httpx.HTTPError as exc:
                return Check(story, "error", f"API request failed: {exc}")

        return list(await asyncio.gather(*(check(s) for s in digest.stories)))
    finally:
        if owns_client:
            await client.aclose()
