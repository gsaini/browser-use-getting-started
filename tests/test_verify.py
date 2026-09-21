import asyncio

import httpx

from hn_digest.models import Digest
from hn_digest.verify import compare, verify


def test_matching_story_is_verified(story, item):
    check = compare(story, item)
    assert check.ok and check.detail == ""


def test_whitespace_and_case_differences_are_ignored(story, item):
    story = story.model_copy(update={"title": "  what sun  got WRONG "})
    assert compare(story, item).ok


def test_score_drift_is_reported_but_still_verified(story, item):
    check = compare(story, {**item, "score": 150})
    assert check.ok
    assert "score now 150" in check.detail


def test_hallucinated_title_is_a_mismatch(story, item):
    story = story.model_copy(update={"title": "What Sun Got Right"})
    check = compare(story, item)
    assert check.status == "mismatch" and "title" in check.detail


def test_wrong_url_is_a_mismatch(story, item):
    story = story.model_copy(update={"url": "https://example.com/other"})
    assert compare(story, item).status == "mismatch"


def test_text_post_without_url_is_fine(story, item):
    story = story.model_copy(update={"url": None})
    item = {k: v for k, v in item.items() if k != "url"}
    assert compare(story, item).ok


def test_missing_item_id(story):
    assert compare(story.model_copy(update={"item_id": None}), None).status == "missing_id"


def test_unknown_item(story):
    assert compare(story, None).status == "not_found"


def test_verify_looks_up_every_story_offline(story, item):
    unknown = story.model_copy(update={"rank": 2, "item_id": 1})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(f"/{item['id']}.json"):
            return httpx.Response(200, json=item)
        return httpx.Response(200, content=b"null")  # the API answers null for unknown ids

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify(Digest(stories=[story, unknown]), client)

    checks = asyncio.run(run())
    assert [c.status for c in checks] == ["verified", "not_found"]


def test_api_failure_becomes_an_error_check(story):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await verify(Digest(stories=[story]), client)

    (check,) = asyncio.run(run())
    assert check.status == "error"
