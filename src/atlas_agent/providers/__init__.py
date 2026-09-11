"""Provider factory and exports for atlas-agent."""
from __future__ import annotations
from typing import Optional
from atlas_agent.config import Config
from atlas_agent.providers.base import (
    BaseProvider, Message, ProviderResponse, ToolCall, ToolResult
)
from atlas_agent.providers.gemini import GeminiProvider
from atlas_agent.providers.openai_compat import OpenAICompatibleProvider
from atlas_agent.providers.mock import MockProvider

__all__ = [
    "BaseProvider",
    "Message",
    "ProviderResponse",
    "ToolCall",
    "ToolResult",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "MockProvider",
    "create_provider"
]

def create_provider(config: Config) -> BaseProvider:
    """Factory creating the appropriate provider based on configuration."""
    provider_type = (config.provider or "gemini").lower()

    if provider_type == "gemini":
        return GeminiProvider(
            api_key=config.api_key,
            model=config.model or "gemini-2.5-flash",
            endpoint=config.endpoint,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            max_retries=config.max_retries
        )
    elif provider_type in ("openai", "openai-compatible", "openrouter", "ollama", "local"):
        default_model = "google/gemini-2.5-flash" if provider_type == "openrouter" else "gpt-4o-mini"
        default_endpoint = "https://openrouter.ai/api/v1" if provider_type == "openrouter" else "https://api.openai.com/v1"
        return OpenAICompatibleProvider(
            api_key=config.api_key,
            model=config.model if (config.model and config.model != "gemini-2.5-flash") else default_model,
            endpoint=config.endpoint or default_endpoint,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            max_retries=config.max_retries
        )
    elif provider_type == "mock":
        return MockProvider()
    else:
        raise ValueError(f"Unknown provider: '{config.provider}'. Supported: gemini, openai, mock")
