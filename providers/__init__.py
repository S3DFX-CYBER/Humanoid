"""LLM providers and connection pool."""

from providers.base import Provider, ProviderError, ProviderStatus
from providers.gemini import GeminiProvider
from providers.openai import OpenAIProvider
from providers.pool import ProviderExhaustedError, ProviderPool
from providers.stub import StubProvider


def get_provider_pool() -> ProviderPool:
    """Initialize a ProviderPool configured with Gemini and OpenAI."""
    # Create providers
    from api.config import get_settings

    settings = get_settings()
    providers = [OpenAIProvider("gpt-4o-mini")]
    if settings.gemini_api_key:
        providers.insert(0, GeminiProvider(settings.gemini_api_key))

    # Optional: configure fallback tiers or just leave them all "cheap" default
    # With default tiers, the pool load balances by provider order.

    return ProviderPool(providers=providers)


__all__ = [
    "Provider",
    "ProviderError",
    "ProviderStatus",
    "GeminiProvider",
    "OpenAIProvider",
    "StubProvider",
    "ProviderPool",
    "ProviderExhaustedError",
    "get_provider_pool",
]
