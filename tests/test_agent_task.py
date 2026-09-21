import pytest

from hn_digest.__main__ import parse_args
from hn_digest.agent import build_task


def test_front_page_needs_no_navigation_click():
    task = build_task("front", 5)
    assert task.startswith("Open https://news.ycombinator.com.")
    assert "first 5 stories" in task


def test_sections_are_reached_through_the_nav_bar():
    assert "click 'show' in the top navigation bar" in build_task("show", 5)


def test_topic_filter_allows_fewer_results():
    task = build_task("front", 5, topic="databases")
    assert "'databases'" in task and "fewer than 5" in task


def test_task_forbids_guessing_and_side_effects():
    task = build_task("new", 3)
    assert "Never guess" in task and "do not log in or vote" in task


@pytest.mark.parametrize("count", ["0", "31"])
def test_count_is_bounded(count):
    with pytest.raises(SystemExit):
        parse_args(["--count", count])
