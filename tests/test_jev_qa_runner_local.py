"""End-to-end run of the loop with a real Chromium and a *fake* Jev over a local page.

No network and no API key: a tiny HTTP server serves a login page from tmp_path and the
scripted `ask` plays Jev. Skipped when Playwright's Chromium is not installed (CI does not
install browsers), so `uv run pytest -q` stays offline everywhere.
"""

import asyncio
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, SystemOneResponse, Usage

from jev_qa.runner import run
from jev_qa.spec import parse_spec

LOGIN_HTML = """<!doctype html><title>Login</title><h2>Login Page</h2>
<p>This is where you can log into the secure area.</p>
<div id="flash" hidden></div>
<form id="f"><label>Username <input name="username"></label>
<label>Password <input name="password" type="password"></label>
<button type="submit">Login</button></form>
<a href="https://elementalselenium.com/">Elemental Selenium</a>
<script>
document.getElementById('f').onsubmit = e => {
  e.preventDefault();
  if (e.target.password.value === 'pw') location.href = 'secure.html';
  else {
    const f = document.getElementById('flash');
    f.hidden = false; f.textContent = 'Your password is invalid!';
  }
};
</script>"""
SECURE_HTML = """<!doctype html><title>Secure</title><h2>Secure Area</h2>
<p>You logged into a secure area!</p><a href="/logout">Logout</a>"""


def chromium_available() -> bool:
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not chromium_available(), reason="Playwright Chromium not installed"
)


@pytest.fixture
def site(tmp_path):
    (tmp_path / "login.html").write_text(LOGIN_HTML, encoding="utf-8")
    (tmp_path / "secure.html").write_text(SECURE_HTML, encoding="utf-8")
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a, **k: None  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def spec_for(site, password="pw"):
    return parse_spec(
        {
            "id": "local-login",
            "start_url": f"{site}/login.html",
            "goal": "Log in with the prepared username and password. "
            "Done when the secure area is shown.",
            "data": {"username": "tomsmith", "password": password},
            "secrets": ["password"],
            "outcomes": {
                "logged_in": {"when": "The page heading says 'Secure Area'.", "verdict": "pass"},
                "rejected": {
                    "when": "A flash message says your password is invalid.",
                    "verdict": "bug",
                },
            },
            "assert": [
                {"url_matches": "**/secure.html"},
                {"text_contains": "You logged into a secure area!"},
                {"element_present": "a[href='/logout']"},
            ],
        }
    )


def choice(pick, keys, confidence=0.95):
    keys = list(keys)
    rest = (1 - confidence) / max(1, len(keys) - 1)
    return ChoiceAnswer(
        type="choice",
        choice=pick,
        confidence=confidence,
        probabilities={k: confidence if k == pick else rest for k in keys},
    )


def fake_jev(*, claim_done_first=False):
    """Plays Jev: fills each empty field with its prepared value, clicks Login, then judges."""
    calls = []

    async def ask(state, questions):
        calls.append(state)
        text = state["page"]["text"]
        answers = {}
        for key in [k for k in questions if k.startswith("outcome:")]:
            name = key.split(":", 1)[1]
            seen = ("Secure Area" in text) if name == "logged_in" else ("invalid" in text)
            answers[key] = NoulAnswer(type="noul", noul=0.96 if seen else 0.03)
        if "operation" in questions:
            ops = questions["operation"].criteria
            elements = {e["element"]: e for e in state["elements"]}
            empty = [e for e in elements if "textbox" in e and "current_value" not in elements[e]]
            login = next((e for e in elements if "button 'Login'" in e), None)
            if claim_done_first and len(calls) == 1:
                answers["operation"] = choice("DONE", ops)
            elif empty and "TYPE_TEXT" in ops:
                idx = empty[0].split("]")[0][1:]
                value = "username" if "Username" in empty[0] else "password"
                answers["operation"] = choice("TYPE_TEXT", ops)
                answers["type_target"] = choice(idx, questions["type_target"].criteria)
                answers["type_value"] = choice(value, questions["type_value"].criteria)
            elif login and "CLICK" in ops:
                answers["operation"] = choice("CLICK", ops)
                answers["click_target"] = choice(
                    login.split("]")[0][1:], questions["click_target"].criteria
                )
            else:
                answers["operation"] = choice("WAIT", ops)
        return SystemOneResponse(
            model="fake-jev", usage=Usage(input_tokens=100, output_tokens=0), answers=answers
        )

    ask.calls = calls  # type: ignore[attr-defined]
    return ask


def test_correct_password_passes_with_evidence_and_artifacts(site, tmp_path):
    ask = fake_jev()
    result = asyncio.run(run(spec_for(site), out_dir=tmp_path / "runs", ask=ask))

    assert (result.status, result.verdict, result.outcome) == ("passed", "pass", "logged_in")
    assert [s.operation for s in result.steps] == ["TYPE_TEXT", "TYPE_TEXT", "CLICK", "WAIT"]
    assert all(s.executed for s in result.steps[:3]) and result.steps[3].note.startswith(
        "outcome logged_in seen"
    )
    assert result.evidence == "Secure Area"
    assert [a.ok for a in result.assertions] == [True, True, True]
    assert result.final_url.endswith("/secure.html") and result.exit_code == 0
    assert (
        result.jev_requests == 4 and result.model == "fake-jev" and result.jev_input_tokens == 400
    )

    run_dir = tmp_path / "runs" / "local-login"
    (stamp,) = list(run_dir.iterdir())
    written = json.loads((stamp / "result.json").read_text())
    assert written["verdict"] == "pass" and (stamp / "steps" / "004.png").exists()
    trace = (stamp / "trace.json").read_text()
    assert "pw" not in json.dumps(json.loads(trace)["spec"]["data"]) and "<secret>" in trace
    # Jev only ever saw the placeholder for the password, and "(filled)" once it was typed.
    assert ask.calls[0]["prepared_values"]["password"] == "<secret>"
    assert ask.calls[2]["elements"][1]["current_value"] == "(filled)"


def test_wrong_password_reaches_the_declared_bug_outcome(site, tmp_path):
    result = asyncio.run(run(spec_for(site, password="nope"), out_dir=None, ask=fake_jev()))

    assert (result.status, result.verdict, result.outcome) == ("outcome", "bug", "rejected")
    assert result.evidence == "Your password is invalid!"
    assert result.exit_code == 1 and result.out_dir is None


def test_done_claimed_too_early_is_not_a_pass(site):
    result = asyncio.run(run(spec_for(site), ask=fake_jev(claim_done_first=True)))

    assert result.status == "done_unverified" and result.verdict == "undetermined"
    assert result.suggested_verdict == "test_issue" and result.steps[0].note.startswith(
        "DONE claimed"
    )
