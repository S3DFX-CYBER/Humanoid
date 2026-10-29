"""Provider pool with retry, backoff, cooldown, and tiered routing."""

import asyncio
import logging
import random
from datetime import timedelta

from providers.base import (
    Provider,
    ProviderError,
    ProviderExhaustedError,
    ProviderFatalError,
    utcnow,
)

logger = logging.getLogger(__name__)

BASE_COOLDOWN_SECONDS = 30
MAX_COOLDOWN_SECONDS = 300
# A provider rejected our credentials — leave it parked for an hour.
FATAL_COOLDOWN_SECONDS = 3600
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0
FAILURES_BEFORE_COOLDOWN = 2


class ProviderPool:
    """Manages a pool of LLM providers with retry, backoff, and tiered routing.

    Usage:
        pool = ProviderPool(providers=[gemini, openai])
        result = await pool.call("Write an essay about X", tier="premium")
    """

    def __init__(self, providers: list[Provider]):
        if not providers:
            raise ValueError("ProviderPool requires at least one provider")
        self.providers = providers

    def _available(self, tier: str) -> list[Provider]:
        """Return available providers, tier matches first."""
        now = utcnow()
        available: list[Provider] = []

        for provider in self.providers:
            cooldown_until = provider.status.cooldown_until
            if cooldown_until is not None:
                if now < cooldown_until:
                    continue
                provider.status.cooldown_until = None
                provider.status.is_available = True
            if provider.status.is_available:
                available.append(provider)

        tier_matched = [p for p in available if p.tier == tier]
        if tier_matched:
            others = [p for p in available if p.tier != tier]
            return tier_matched + others
        return available

    def _cool_down(self, provider: Provider, seconds: int, reason: str) -> None:
        provider.status.cooldown_until = utcnow() + timedelta(seconds=seconds)
        provider.status.is_available = False
        logger.warning(
            "[ProviderPool] %s parked for %ss (%s)",
            provider.name,
            seconds,
            reason,
        )

    async def call(self, prompt: str, tier: str = "cheap", **kwargs) -> str:
        """Route a prompt through the pool with retry + backoff.

        Args:
            prompt: The prompt to send.
            tier: "cheap" for structured/verification calls, "premium" for drafting.

        Raises:
            ProviderExhaustedError: If every provider and retry is exhausted.
            ProviderFatalError: If every provider rejected our credentials.
        """
        return await self._call(prompt, tier, json_mode=False, **kwargs)

    async def call_json(self, prompt: str, tier: str = "cheap", **kwargs) -> str:
        """Like :meth:`call`, but asks the provider for a JSON response."""
        return await self._call(prompt, tier, json_mode=True, **kwargs)

    async def _call(
        self, prompt: str, tier: str, json_mode: bool, **kwargs
    ) -> str:
        last_error: Exception | None = None
        fatal_errors = 0

        for attempt in range(MAX_RETRIES):
            providers = self._available(tier)

            if not providers:
                wait = BASE_BACKOFF_SECONDS * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    "[ProviderPool] no providers available, waiting %.1fs "
                    "(attempt %d/%d)",
                    wait,
                    attempt + 1,
                    MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                continue

            for provider in providers:
                try:
                    if json_mode:
                        return await provider.complete_json(prompt, **kwargs)
                    return await provider.complete(prompt, **kwargs)

                except ProviderFatalError as exc:
                    # Bad credentials: park this provider, try the next one.
                    fatal_errors += 1
                    last_error = exc
                    provider.record_error(str(exc))
                    self._cool_down(provider, FATAL_COOLDOWN_SECONDS, "fatal error")
                    logger.error(
                        "[ProviderPool] %s fatal: %s", provider.name, exc
                    )
                    continue

                except ProviderError as exc:
                    last_error = exc
                    provider.record_error(str(exc))
                    logger.warning(
                        "[ProviderPool] %s failed (attempt %d/%d): %s",
                        provider.name,
                        attempt + 1,
                        MAX_RETRIES,
                        exc,
                    )
                    if provider.status.consecutive_failures >= FAILURES_BEFORE_COOLDOWN:
                        backoff = min(
                            BASE_COOLDOWN_SECONDS
                            * 2 ** (provider.status.consecutive_failures - 1),
                            MAX_COOLDOWN_SECONDS,
                        )
                        self._cool_down(provider, backoff, "repeated failures")
                    continue

            wait = BASE_BACKOFF_SECONDS * (2**attempt) + random.uniform(0, 1)
            logger.info("[ProviderPool] backing off %.1fs before retry", wait)
            await asyncio.sleep(wait)

        if fatal_errors and fatal_errors >= len(self.providers):
            raise ProviderFatalError(
                f"Every provider rejected our credentials. Last error: {last_error}"
            )

        raise ProviderExhaustedError(
            f"All providers exhausted after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )
