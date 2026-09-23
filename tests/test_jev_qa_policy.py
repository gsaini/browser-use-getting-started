import pytest
from typesafe_sdk import Choice, ChoiceAnswer, Noul, NoulAnswer

from jev_qa.observe import Element, Observation
from jev_qa.policy import (
    PolicyError,
    build_questions,
    build_state,
    evidence_line,
    outcome_questions,
    read_decision,
    read_outcomes,
)
from jev_qa.spec import parse_spec


@pytest.fixture
def spec():
    return parse_spec(
        {
            "id": "login",
            "start_url": "https://example.test/login",
            "goal": "Log in and reach the secure area.",
            "data": {"username": "tomsmith", "password": "pw"},
            "secrets": ["password"],
            "outcomes": {
                "logged_in": {"when": "The page heading says 'Secure Area'.", "verdict": "pass"},
                "no_change": {
                    "when": "The login form is still shown.",
                    "verdict": "bug",
                    "requires_action": True,
                },
            },
            "assert": [{"url_matches": "**/secure"}],
        }
    )


@pytest.fixture
def obs():
    return Observation(
        url="https://example.test/login",
        title="Login",
        text="Login Page\nThis is where you can log into the secure area.\n"
        "Username\nPassword\nLogin",
        elements=[
            Element(idx=1, role="textbox", name="Username"),
            Element(idx=2, role="textbox", name="Password"),
            Element(idx=3, role="button", name="Login"),
            Element(idx=4, role="link", name="Elemental Selenium"),
        ],
    )


def answer(choice, keys, confidence=0.9):
    rest = (1 - confidence) / max(1, len(keys) - 1)
    probs = {k: (confidence if k == choice else rest) for k in keys}
    return ChoiceAnswer(type="choice", choice=choice, confidence=confidence, probabilities=probs)


def test_questions_offer_only_what_the_page_supports(spec, obs):
    questions, offered = build_questions(spec, obs, typed_before=False)
    assert offered.operations == ("CLICK", "TYPE_TEXT", "WAIT", "DONE", "BLOCKED")
    assert offered.click_targets == ("3", "4")  # textboxes are typed into, not clicked
    assert offered.type_targets == ("1", "2")
    assert offered.values == ("username", "password")
    assert set(questions) == {
        "operation",
        "click_target",
        "type_target",
        "type_value",
        "outcome:logged_in",
        "outcome:no_change",
    }
    assert isinstance(questions["operation"], Choice)
    assert isinstance(questions["outcome:logged_in"], Noul)
    assert questions["type_value"].criteria["password"]["value"] == "<secret>"


def test_press_enter_and_scroll_appear_only_when_possible(spec, obs):
    _, offered = build_questions(spec, obs, typed_before=True)
    assert "PRESS_ENTER" in offered.operations
    scrolled = obs.model_copy(update={"can_scroll_down": True})
    _, offered = build_questions(spec, scrolled, typed_before=False)
    assert "SCROLL_DOWN" in offered.operations and "SCROLL_UP" not in offered.operations


def test_type_text_needs_prepared_values(spec, obs):
    no_data = spec.model_copy(update={"data": {}, "secrets": []})
    _, offered = build_questions(no_data, obs, typed_before=False)
    assert "TYPE_TEXT" not in offered.operations and offered.values == ()


def test_state_masks_secrets_and_windows_history(spec, obs):
    history = [{"action": f"a{i}"} for i in range(15)]
    state = build_state(spec, obs, history, step=16)
    assert state["prepared_values"] == {"username": "tomsmith", "password": "<secret>"}
    assert len(state["recent_actions"]) == 10 and state["recent_actions"][-1]["action"] == "a14"
    assert state["elements"][0] == {"element": "[1] textbox 'Username'"}


def test_a_type_decision_reads_target_and_value(spec, obs):
    _, offered = build_questions(spec, obs, typed_before=False)
    answers = {
        "operation": answer("TYPE_TEXT", offered.operations),
        "type_target": answer("1", offered.type_targets),
        "type_value": answer("username", offered.values, 0.8),
        "click_target": answer("3", offered.click_targets),
        "outcome:logged_in": NoulAnswer(type="noul", noul=0.05),
        "outcome:no_change": NoulAnswer(type="noul", noul=0.9),
    }
    d = read_decision(answers, offered, spec)
    assert (d.operation, d.target, d.value_key) == ("TYPE_TEXT", 1, "username")
    assert d.target_confidence == 0.8 and not d.low_confidence(spec)
    assert d.summary() == "TYPE_TEXT (0.90) -> [1] value=username"


def test_requires_action_defers_an_outcome_until_something_ran(spec, obs):
    _, offered = build_questions(spec, obs, typed_before=False)
    answers = {
        "operation": answer("CLICK", offered.operations),
        "click_target": answer("3", offered.click_targets),
        "outcome:logged_in": NoulAnswer(type="noul", noul=0.1),
        "outcome:no_change": NoulAnswer(type="noul", noul=0.95),
    }
    d = read_decision(answers, offered, spec)
    assert d.seen_outcome(spec, acted=False) is None
    assert d.seen_outcome(spec, acted=True) == "no_change"


def test_outcomes_below_threshold_are_not_seen(spec, obs):
    _, offered = build_questions(spec, obs, typed_before=False)
    answers = {
        "operation": answer("WAIT", offered.operations),
        "outcome:logged_in": NoulAnswer(type="noul", noul=0.79),
    }
    d = read_decision(answers, offered, spec)
    assert d.seen_outcome(spec, acted=True) is None
    assert d.outcomes == {"logged_in": 0.79}


@pytest.mark.parametrize(
    "bad",
    [
        lambda o: {
            "operation": answer("CLICK", o.operations),
            "click_target": answer("9", ("9", "3")),
        },
        lambda o: {"operation": answer("CLICK", o.operations), "click_target": answer("3", ("3",))},
        lambda o: {"operation": answer("SELECT", (*o.operations, "SELECT"))},
        lambda o: {"operation": None},
        lambda o: {
            "operation": ChoiceAnswer(
                type="choice",
                choice="WAIT",
                confidence=0.5,
                probabilities={k: (0.9 if k == "DONE" else 0.1 / 4) for k in o.operations},
            )
        },
    ],
)
def test_answers_that_do_not_fit_the_menu_are_rejected(spec, obs, bad):
    _, offered = build_questions(spec, obs, typed_before=False)
    with pytest.raises(PolicyError):
        read_decision(bad(offered), offered, spec)


def test_low_confidence_is_flagged_not_executed(spec, obs):
    _, offered = build_questions(spec, obs, typed_before=False)
    d = read_decision({"operation": answer("WAIT", offered.operations, 0.4)}, offered, spec)
    assert d.low_confidence(spec)


def test_outcome_only_questions_for_the_recheck(spec):
    qs = outcome_questions(spec)
    assert set(qs) == {"outcome:logged_in", "outcome:no_change"}
    got = read_outcomes({"outcome:logged_in": NoulAnswer(type="noul", noul=1.4)}, spec)
    assert got == {"logged_in": 1.0}


def test_evidence_line_quotes_the_best_matching_page_line():
    text = "Login Page\nWelcome to the Secure Area. When you are done click logout below.\nLogout"
    assert evidence_line(text, "The page heading says 'Secure Area'.").startswith(
        "Welcome to the Secure Area"
    )
    assert evidence_line("nothing relevant here", "The page heading says 'Secure Area'.") == ""
