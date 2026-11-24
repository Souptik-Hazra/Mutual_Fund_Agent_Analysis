"""Lazy LangChain chat-model factory for supported providers."""

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from mutual_fund_agent_analysis.core.config import get_settings

Provider = Literal["gemini", "groq", "openai"]


def create_chat_model(
    provider: Provider | None = None,
    model: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Create a chat model on demand; no provider is contacted during API startup."""
    settings = get_settings()
    selected = provider or settings.llm_provider

    if selected == "gemini":
        key, name = settings.gemini_api_key, model or settings.gemini_model
        if key is None or not name:
            raise ValueError("GEMINI_API_KEY and GEMINI_MODEL are required for Gemini.")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=name, google_api_key=key.get_secret_value(), temperature=temperature
        )

    if selected == "groq":
        key, name = settings.groq_api_key, model or settings.groq_model
        if key is None or not name:
            raise ValueError("GROQ_API_KEY and GROQ_MODEL are required for Groq.")
        from langchain_groq import ChatGroq

        return ChatGroq(model=name, api_key=key.get_secret_value(), temperature=temperature)

    if selected == "openai":
        key, name = settings.openai_api_key, model or settings.openai_model
        if key is None or not name:
            raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required for OpenAI.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=name, api_key=key.get_secret_value(), temperature=temperature)

    raise ValueError(f"Unsupported LLM provider: {selected}")
