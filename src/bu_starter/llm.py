"""One place to choose the model that every example and the app use.

Pick a provider with LLM_PROVIDER in your .env:

    anthropic    (default)  Claude, via ANTHROPIC_API_KEY.
                            Model from ANTHROPIC_MODEL, default claude-opus-5.
    browser-use             Browser Use's own BU2 model, via BROWSER_USE_API_KEY.

browser-use supports many more providers (OpenAI, Gemini, Ollama, ...). To use
one, construct its Chat* class here — the rest of the code doesn't change.
"""

from __future__ import annotations

import os

from browser_use import ChatAnthropic, ChatBrowserUse

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"

# If Claude Opus 5 declines a request, the API retries it server-side on this
# model instead of failing the step (browser-use adds the beta header).
OPUS_5_FALLBACKS = [{"model": "claude-opus-4-8"}]


class MissingCredentials(RuntimeError):
    """Raised when the selected provider has no API key configured."""


def get_llm() -> ChatAnthropic | ChatBrowserUse:
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

    if provider == "anthropic":
        if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
            raise MissingCredentials(
                "LLM_PROVIDER=anthropic needs ANTHROPIC_API_KEY in your .env "
                "(copy .env.example to .env and fill it in)."
            )
        model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        fallbacks = OPUS_5_FALLBACKS if model == "claude-opus-5" else None
        return ChatAnthropic(model=model, fallbacks=fallbacks)

    if provider in {"browser-use", "browser_use", "bu"}:
        if not os.getenv("BROWSER_USE_API_KEY"):
            raise MissingCredentials(
                "LLM_PROVIDER=browser-use needs BROWSER_USE_API_KEY in your .env "
                "(get one at https://cloud.browser-use.com/new-api-key)."
            )
        return ChatBrowserUse(model=os.getenv("BROWSER_USE_MODEL", "bu-2-0"))

    raise ValueError(f"Unknown LLM_PROVIDER {provider!r} — use 'anthropic' or 'browser-use'.")
