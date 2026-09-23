import json

import pytest

from jev_qa.spec import SpecError, load_spec, parse_spec

BASE = {
    "id": "login",
    "start_url": "https://example.test/login",
    "goal": "Log in and reach the secure area.",
    "data": {"username": "tomsmith", "password": "${DEMO_PASS}"},
    "secrets": ["password"],
    "outcomes": {
        "logged_in": {"when": "The page heading says 'Secure Area'.", "verdict": "pass"},
        "rejected": {"when": "A flash message says the password is invalid.", "verdict": "bug"},
    },
    "assert": [{"url_matches": "**/secure"}, {"text_contains": "secure area"}],
}


def test_valid_spec_parses_with_assert_alias():
    spec = parse_spec(BASE)
    assert spec.id == "login" and len(spec.assertions) == 2
    assert spec.assertions[0].kind == "url_matches" and spec.assertions[0].arg == "**/secure"
    assert spec.hosts == ["example.test"]


def test_json_string_is_accepted_and_bad_json_is_a_spec_error():
    assert parse_spec(json.dumps(BASE)).id == "login"
    with pytest.raises(SpecError, match="not valid JSON"):
        parse_spec("{not json")


def test_a_pass_outcome_is_required():
    bad = {**BASE, "outcomes": {"rejected": BASE["outcomes"]["rejected"]}}
    with pytest.raises(SpecError, match="verdict 'pass'"):
        parse_spec(bad)


@pytest.mark.parametrize(
    "assertion", [{}, {"url_matches": "a", "text_contains": "b"}, {"nope": "x"}]
)
def test_an_assertion_sets_exactly_one_known_check(assertion):
    with pytest.raises(SpecError):
        parse_spec({**BASE, "assert": [assertion]})


def test_secrets_must_be_data_keys():
    with pytest.raises(SpecError, match="secrets must name keys of data"):
        parse_spec({**BASE, "secrets": ["token"]})


def test_env_references_are_resolved_or_reported():
    spec = parse_spec(BASE)
    assert spec.with_env({"DEMO_PASS": "pw"}).data["password"] == "pw"
    with pytest.raises(SpecError, match=r"data.password needs \$\{DEMO_PASS\}"):
        spec.with_env({})


def test_env_reference_with_default():
    spec = parse_spec({**BASE, "data": {"username": "u", "password": "${DEMO_PASS:-fallback!}"}})
    assert spec.with_env({}).data["password"] == "fallback!"
    assert spec.with_env({"DEMO_PASS": "real"}).data["password"] == "real"


def test_secret_values_never_appear_in_previews():
    spec = parse_spec(BASE).with_env({"DEMO_PASS": "pw"})
    assert spec.preview("password") == "<secret>" and spec.preview("username") == "tomsmith"
    assert spec.secret_values() == ["pw"]


def test_load_spec_reads_a_file_and_resolves_env(tmp_path, monkeypatch):
    path = tmp_path / "login.json"
    path.write_text(json.dumps(BASE), encoding="utf-8")
    monkeypatch.setenv("DEMO_PASS", "pw")
    assert load_spec(path).data["password"] == "pw"
    with pytest.raises(SpecError, match="spec not found"):
        load_spec(tmp_path / "missing.json")


def test_unknown_fields_are_rejected():
    with pytest.raises(SpecError):
        parse_spec({**BASE, "steps": 3})
