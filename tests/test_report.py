from datetime import UTC, datetime

from hn_digest.report import RunMeta, render_markdown, to_record
from hn_digest.verify import Check

META = RunMeta(
    section="show",
    topic=None,
    model="claude-opus-5",
    steps=6,
    seconds=21.5,
    tokens=18_000,
    cost_usd=0.1234,
    generated_at=datetime(2026, 9, 21, 9, 30, tzinfo=UTC),
)


def test_markdown_has_summary_and_row(story):
    md = render_markdown([Check(story, "verified")], META)
    assert "# Hacker News digest — show" in md
    assert "**1/1 verified**" in md
    assert "`claude-opus-5`" in md and "$0.1234" in md
    assert "[What Sun Got Wrong](https://bcantrill.dtrace.org/" in md
    assert "item?id=49787436" in md and "| ✅ |" in md


def test_titles_cannot_break_the_table(story):
    story = story.model_copy(update={"title": "A | B [draft]"})
    md = render_markdown([Check(story, "verified")], META)
    assert r"A \| B \[draft\]" in md


def test_problems_are_listed_as_notes(story):
    md = render_markdown([Check(story, "mismatch", "title: page 'x' vs API 'y'")], META)
    assert "**0/1 verified**" in md and "| ❌ |" in md
    assert "#1 mismatch: title" in md


def test_empty_topic_result():
    md = render_markdown([], RunMeta(**{**META.__dict__, "topic": "databases"}))
    assert "topic: databases" in md and "_No matching stories._" in md


def test_json_record(story):
    record = to_record([Check(story, "verified", "score now 150 (page showed 103)")], META)
    assert record["stories"][0]["check"] == "verified"
    assert record["stories"][0]["item_id"] == 49787436
    assert record["generated_at"] == "2026-09-21T09:30:00+00:00"
