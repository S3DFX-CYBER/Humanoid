"""LLM providers and connection pool."""

from providers.base import Provider, ProviderError, ProviderStatus
from providers.gemini import GeminiProvider
from providers.openai import OpenAIProvider
from providers.pool import ProviderPool
from providers.stub import StubProvider


def get_provider_pool() -> ProviderPool:
    """Initialize a ProviderPool configured with Gemini and OpenAI."""
    # Create providers
    gemini = GeminiProvider("gemini-2.5-flash")
    openai = OpenAIProvider("gpt-4o-mini")

    # Optional: configure fallback tiers or just leave them all "cheap" default
    # With default tiers, the pool load balances by provider order.

    pool = ProviderPool(providers=[gemini, openai])
    return pool


__all__ = [
    "Provider",
    "ProviderError",
    "ProviderStatus",
    "GeminiProvider",
    "OpenAIProvider",
    "StubProvider",
    "ProviderPool",
    "get_provider_pool",
]
