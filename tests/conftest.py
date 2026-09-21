import pytest

from hn_digest.models import Story


@pytest.fixture
def story() -> Story:
    return Story(
        rank=1,
        title="What Sun Got Wrong",
        url="https://bcantrill.dtrace.org/2026/09/20/what-sun-got-wrong/",
        points=103,
        comments=48,
        author="chmaynard",
        item_id=49787436,
    )


@pytest.fixture
def item() -> dict:
    """Shape of https://hacker-news.firebaseio.com/v0/item/<id>.json"""
    return {
        "by": "chmaynard",
        "descendants": 48,
        "id": 49787436,
        "score": 103,
        "title": "What Sun Got Wrong",
        "type": "story",
        "url": "https://bcantrill.dtrace.org/2026/09/20/what-sun-got-wrong/",
    }
