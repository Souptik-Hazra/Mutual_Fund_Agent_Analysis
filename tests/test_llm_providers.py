"""Tests for lazy LLM provider configuration."""

from types import SimpleNamespace

import pytest

from mutual_fund_agent_analysis.llm import providers


@pytest.mark.parametrize(
    ("provider", "expected_message"),
    [
        ("gemini", "GEMINI_API_KEY and GEMINI_MODEL"),
        ("groq", "GROQ_API_KEY and GROQ_MODEL"),
        ("openai", "OPENAI_API_KEY and OPENAI_MODEL"),
    ],
)
def test_provider_requires_credentials_before_import(
    monkeypatch, provider: str, expected_message: str
) -> None:
    settings = SimpleNamespace(
        llm_provider=provider,
        gemini_api_key=None,
        gemini_model=None,
        groq_api_key=None,
        groq_model=None,
        openai_api_key=None,
        openai_model=None,
    )
    monkeypatch.setattr(providers, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match=expected_message):
        providers.create_chat_model(provider=provider)


def test_provider_factory_rejects_unknown_provider(monkeypatch) -> None:
    settings = SimpleNamespace(llm_provider="unknown")
    monkeypatch.setattr(providers, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        providers.create_chat_model()
