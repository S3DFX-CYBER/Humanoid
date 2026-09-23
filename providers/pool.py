"""Provider routing with retries, fallback, and provider cooldowns."""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from providers.base import Provider, ProviderError, ProviderFatalError, ProviderStatus

logger = logging.getLogger(__name__)

BASE_COOLDOWN_SECONDS = 30
MAX_COOLDOWN_SECONDS = 300
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class ProviderExhaustedError(ProviderError):
    """Raised when every eligible provider has exhausted its retries."""


class ProviderPool:
    """Route completions to tiered providers with reliable fallback behavior.

    ``providers`` is optional to make it easy for applications to register
    providers after configuration has loaded.  The public tier mapping also
    keeps provider selection explicit and inspectable for health checks.
    """

    def __init__(self, providers: list[Provider] | None = None):
        self.providers: dict[str, list[Provider]] = {}
        self.status: dict[str, ProviderStatus] = {}
        for provider in providers or []:
            self.add(provider)

    def add(self, provider: Provider) -> None:
        """Register a provider in its configured tier."""
        self.providers.setdefault(provider.tier, []).append(provider)
        self.status[provider.name] = provider.status

    def _get_available_providers(self, tier: str) -> list[Provider]:
        """Return available providers, preferring the requested tier."""
        now = datetime.now(timezone.utc)
        candidates = self.providers.get(tier, [])
        if not candidates:
            candidates = [
                provider
                for group in self.providers.values()
                for provider in group
            ]

        available = []
        for provider in candidates:
            self.status[provider.name] = provider.status
            cooldown_until = provider.status.cooldown_until
            if cooldown_until and cooldown_until.tzinfo is None:
                cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
                provider.status.cooldown_until = cooldown_until
            if cooldown_until and now < cooldown_until:
                continue
            if cooldown_until:
                provider.status.cooldown_until = None
                provider.status.is_available = True
            if provider.status.is_available:
                available.append(provider)
        return available

    def _apply_cooldown(self, provider: Provider) -> None:
        failures = provider.status.consecutive_failures
        seconds = min(
            BASE_COOLDOWN_SECONDS * (2 ** (failures - 1)), MAX_COOLDOWN_SECONDS
        )
        provider.status.cooldown_until = datetime.now(timezone.utc) + timedelta(
            seconds=seconds
        )
        provider.status.is_available = False
        logger.warning("[ProviderPool] %s in cooldown for %ds", provider.name, seconds)

    async def call(self, prompt: str, tier: str = "cheap", **kwargs: object) -> str:
        """Complete a prompt, retrying each provider before trying its fallback."""
        last_error: Exception | None = None
        providers = self._get_available_providers(tier)
        if not providers:
            raise ProviderExhaustedError("No providers are currently available")

        for provider in providers:
            for attempt in range(MAX_RETRIES):
                previous_failures = provider.status.consecutive_failures
                try:
                    result = await provider.complete(prompt, **kwargs)
                    provider.mark_success()
                    return result
                except ProviderFatalError:
                    raise
                except Exception as error:  # providers may raise SDK-specific errors
                    last_error = error
                    if provider.status.consecutive_failures == previous_failures:
                        provider.mark_failure()
                    self.status[provider.name] = provider.status
                    logger.warning(
                        "[ProviderPool] %s failed (attempt %d/%d): %s",
                        provider.name,
                        attempt + 1,
                        MAX_RETRIES,
                        error,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(
                            BASE_BACKOFF_SECONDS * (2**attempt) + random.uniform(0, 1)
                        )

            self._apply_cooldown(provider)

        raise ProviderExhaustedError(
            "All providers exhausted after "
            f"{MAX_RETRIES} attempts. Last error: {last_error}"
        )
