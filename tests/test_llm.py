import pytest
from browser_use import ChatAnthropic, ChatBrowserUse

from bu_starter.llm import MissingCredentials, get_llm

KEYS = [
    "LLM_PROVIDER",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "BROWSER_USE_API_KEY",
    "BROWSER_USE_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


def test_default_is_claude_opus_5_with_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    llm = get_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-opus-5"
    assert llm.fallbacks == [{"model": "claude-opus-4-8"}]


def test_model_override_drops_the_opus_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    llm = get_llm()
    assert llm.model == "claude-sonnet-5" and llm.fallbacks is None


def test_missing_key_fails_early_with_a_hint():
    with pytest.raises(MissingCredentials, match="ANTHROPIC_API_KEY"):
        get_llm()


def test_browser_use_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "browser-use")
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    llm = get_llm()
    assert isinstance(llm, ChatBrowserUse) and llm.model == "bu-2-0"


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm()
