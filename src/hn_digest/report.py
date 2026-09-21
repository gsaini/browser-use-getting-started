"""Turn verified stories into a Markdown digest and a JSON record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hn_digest.verify import Check

HN_ITEM = "https://news.ycombinator.com/item?id={id}"
ICONS = {"verified": "✅", "mismatch": "❌", "missing_id": "⚠️", "not_found": "❌", "error": "⚠️"}


@dataclass(frozen=True)
class RunMeta:
    section: str
    topic: str | None
    model: str
    steps: int
    seconds: float
    tokens: int | None
    cost_usd: float | None
    generated_at: datetime


def _escape(text: str) -> str:
    """Keep titles from breaking the Markdown table or link syntax."""
    for char in "\\|[]":
        text = text.replace(char, "\\" + char)
    return text


def _usage(meta: RunMeta) -> str:
    parts = [f"{meta.steps} steps", f"{meta.seconds:.1f}s"]
    if meta.tokens:
        parts.append(f"{meta.tokens:,} tokens")
    if meta.cost_usd:
        parts.append(f"${meta.cost_usd:.4f}")
    return " · ".join(parts)


def render_markdown(checks: list[Check], meta: RunMeta) -> str:
    verified = sum(c.ok for c in checks)
    heading = f"# Hacker News digest — {meta.section}"
    if meta.topic:
        heading += f" · topic: {meta.topic}"
    lines = [
        heading,
        "",
        f"> {meta.generated_at:%Y-%m-%d %H:%M UTC} · collected by a browser-use agent "
        f"(`{meta.model}`) in {_usage(meta)} · "
        f"**{verified}/{len(checks)} verified** against the official HN API.",
        "",
    ]
    if not checks:
        lines.append("_No matching stories._")
        return "\n".join(lines) + "\n"

    lines += [
        "| # | Story | Points | Comments | Check |",
        "|--:|-------|-------:|---------:|:-----:|",
    ]
    for check in checks:
        s = check.story
        title = _escape(s.title)
        story = f"[{title}]({s.url})" if s.url else title
        if s.item_id is not None:
            story += f" · [discuss]({HN_ITEM.format(id=s.item_id)})"
        if s.author:
            story += f" · by {_escape(s.author)}"
        points = "" if s.points is None else str(s.points)
        comments = "" if s.comments is None else str(s.comments)
        lines.append(f"| {s.rank} | {story} | {points} | {comments} | {ICONS[check.status]} |")

    notes = [c for c in checks if c.detail]
    if notes:
        lines += ["", "**Verification notes**", ""]
        lines += [f"- #{c.story.rank} {c.status}: {_escape(c.detail)}" for c in notes]
    return "\n".join(lines) + "\n"


def to_record(checks: list[Check], meta: RunMeta) -> dict:
    return {
        "section": meta.section,
        "topic": meta.topic,
        "model": meta.model,
        "generated_at": meta.generated_at.isoformat(),
        "steps": meta.steps,
        "seconds": round(meta.seconds, 2),
        "tokens": meta.tokens,
        "cost_usd": meta.cost_usd,
        "stories": [
            {**c.story.model_dump(), "check": c.status, "check_detail": c.detail} for c in checks
        ],
    }
