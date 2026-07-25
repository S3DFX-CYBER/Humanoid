"""LLM providers and connection pool."""

from providers.base import Provider, ProviderError, ProviderStatus
from providers.gemini import GeminiProvider
from providers.openai import OpenAIProvider
from providers.pool import ProviderPool
from providers.stub import StubProvider

def get_provider_pool() -> ProviderPool:
    """Initialize and return a production ProviderPool configured with Gemini + OpenAI."""
    # Create providers
    gemini = GeminiProvider("gemini-2.5-flash")
    openai = OpenAIProvider("gpt-4o-mini")
    
    # Optional: configure fallback tiers or just leave them all "cheap" default
    # If both are default tier, the pool load balances (with first having priority by order).
    
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
