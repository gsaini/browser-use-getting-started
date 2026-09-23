import pytest

from jev_qa.report import render
from jev_qa.runner import (
    AssertionResult,
    RunResult,
    StepRecord,
    check_text_assertion,
    on_allowed_host,
)
from jev_qa.spec import Assertion


def result(**overrides):
    base = dict(
        spec_id="login",
        status="passed",
        verdict="pass",
        outcome="logged_in",
        evidence="You logged into a secure area!",
        assertions=[AssertionResult(check="url_matches '**/secure'", ok=True, detail="url is x")],
        steps=[
            StepRecord(
                n=1,
                url="u",
                operation="TYPE_TEXT",
                target="[1] textbox 'Username'",
                value_key="username",
                confidence=0.93,
                executed=True,
                jev_ms=300,
            ),
            StepRecord(
                n=2,
                url="u",
                operation="CLICK",
                target="[3] button 'Login'",
                confidence=0.97,
                executed=True,
            ),
            StepRecord(
                n=3,
                url="u",
                operation="WAIT",
                confidence=0.4,
                note="low confidence, not executed (1/3)",
            ),
        ],
        jev_requests=3,
        duration_ms=5800,
        model="jev-1.13.0",
        out_dir="qa/runs/login/2026",
    )
    return RunResult(**{**base, **overrides})


def test_render_has_verdict_evidence_assertions_and_steps():
    text = render(result())
    assert text.startswith(
        "login · PASS · status passed · outcome logged_in · 3 steps · 3 Jev requests · 5.8s"
    )
    assert 'evidence: "You logged into a secure area!"' in text
    assert "assert ok  url_matches '**/secure'" in text
    assert " 1. TYPE_TEXT (0.93) -> [1] textbox 'Username' value=username" in text
    assert " 3. WAIT (0.40)   (not executed)  · low confidence" in text
    assert "run dir: qa/runs/login/2026" in text


def test_render_shows_suggested_verdict_and_reason():
    text = render(
        result(
            status="blocked",
            verdict="undetermined",
            suggested_verdict="test_issue",
            outcome=None,
            reason="Jev chose BLOCKED",
        )
    )
    assert "UNDETERMINED (suggested: test_issue)" in text and "reason: Jev chose BLOCKED" in text


@pytest.mark.parametrize(
    "status, verdict, code",
    [
        ("passed", "pass", 0),
        ("outcome", "bug", 1),
        ("blocked", "undetermined", 1),
        ("error", "undetermined", 2),
    ],
)
def test_exit_codes(status, verdict, code):
    assert result(status=status, verdict=verdict).exit_code == code


def test_url_glob_ignores_query_and_trailing_slash():
    a = Assertion(url_matches="**/secure")
    assert check_text_assertion(a, "https://x.test/secure/?a=1#top", "")[0]
    assert not check_text_assertion(a, "https://x.test/login", "")[0]


def test_text_contains_normalises_whitespace_and_case():
    a = Assertion(text_contains="You logged into a secure area!")
    assert check_text_assertion(a, "u", "  YOU logged\n into a   secure area!  ")[0]
    assert check_text_assertion(a, "u", "Your password is invalid!")[1] == "not in page text"


def test_allowed_hosts_include_subdomains_only():
    assert on_allowed_host("https://app.example.test/x", ["example.test"])
    assert on_allowed_host("about:blank", ["example.test"])
    assert not on_allowed_host("https://evil.test/example.test", ["example.test"])
