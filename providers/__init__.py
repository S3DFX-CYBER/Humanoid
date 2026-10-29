"""LLM providers and connection pool."""

import logging

from api.config import get_settings
from providers.base import (
    Provider,
    ProviderError,
    ProviderExhaustedError,
    ProviderFatalError,
    ProviderStatus,
)
from providers.pool import ProviderPool
from providers.stub import StubProvider

logger = logging.getLogger(__name__)

__all__ = [
    "Provider",
    "ProviderError",
    "ProviderExhaustedError",
    "ProviderFatalError",
    "ProviderStatus",
    "ProviderPool",
    "StubProvider",
    "get_provider_pool",
]


def get_provider_pool() -> ProviderPool:
    """Build the provider pool from configured credentials.

    Routing:
      * ``tier="premium"`` (outline + drafting) prefers Gemini Flash.
      * ``tier="cheap"`` (query generation, verification, styling) prefers
        OpenAI mini, which is cheaper per token, then falls back to Gemini.
    """
    settings = get_settings()
    providers: list[Provider] = []

    if settings.gemini_api_key:
        from providers.gemini import GeminiProvider

        providers.append(
            GeminiProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                tier="premium",
            )
        )
    else:
        logger.warning("[providers] GEMINI_API_KEY is not set")

    if settings.openai_api_key:
        from providers.openai import OpenAIProvider

        providers.append(
            OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                tier="cheap",
            )
        )
    else:
        logger.warning("[providers] OPENAI_API_KEY is not set")

    if not providers:
        if settings.allow_stub_provider:
            logger.error(
                "[providers] no real provider configured — falling back to the "
                "stub provider because ALLOW_STUB_PROVIDER is set"
            )
            providers.append(StubProvider())
        else:
            raise RuntimeError(
                "No LLM provider configured. Set GEMINI_API_KEY and/or "
                "OPENAI_API_KEY (or ALLOW_STUB_PROVIDER=true for local UI work)."
            )

    return ProviderPool(providers=providers)
