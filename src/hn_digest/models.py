"""The shape of the agent's answer.

These models are sent to the LLM as the schema of its final `done` action, so
the field descriptions double as extraction instructions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Story(BaseModel):
    rank: int = Field(description="Position on the page, starting at 1")
    title: str = Field(description="Story title exactly as shown, without the (domain) suffix")
    url: str | None = Field(
        default=None, description="Absolute URL the title links to; null for text posts"
    )
    points: int | None = Field(default=None, description="Points shown; null if not shown")
    comments: int | None = Field(
        default=None, description="Comment count shown; 0 if the link says 'discuss'"
    )
    author: str | None = Field(default=None, description="Username after 'by'")
    item_id: int | None = Field(
        default=None, description="The number in the story's 'item?id=' comments link"
    )


class Digest(BaseModel):
    stories: list[Story] = Field(description="Stories in page order")
