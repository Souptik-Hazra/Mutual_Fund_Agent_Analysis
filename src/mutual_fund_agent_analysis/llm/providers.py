"""Lazy LangChain 1.x chat-model factory for supported providers."""

from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from mutual_fund_agent_analysis.core.config import get_settings

Provider = Literal["gemini", "groq", "openai"]


def create_chat_model(
    provider: Provider | None = None,
    model: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Initialize a provider model lazily through LangChain's unified model API."""
    settings = get_settings()
    selected = provider or settings.llm_provider

    if selected == "gemini":
        key, name = settings.gemini_api_key, model or settings.gemini_model
        model_provider = "google_genai"
        provider_options = {"google_api_key": key.get_secret_value()} if key else {}
    elif selected == "groq":
        key, name = settings.groq_api_key, model or settings.groq_model
        model_provider = "groq"
        provider_options = {"api_key": key.get_secret_value()} if key else {}
    elif selected == "openai":
        key, name = settings.openai_api_key, model or settings.openai_model
        model_provider = "openai"
        provider_options = {"api_key": key.get_secret_value()} if key else {}
    else:
        raise ValueError(f"Unsupported LLM provider: {selected}")

    if key is None or not name:
        env_name = {"gemini": "GEMINI", "groq": "GROQ", "openai": "OPENAI"}[selected]
        raise ValueError(f"{env_name}_API_KEY and {env_name}_MODEL are required for {selected}.")

    return init_chat_model(
        name,
        model_provider=model_provider,
        temperature=temperature,
        max_retries=2,
        timeout=45,
        **provider_options,
    )
