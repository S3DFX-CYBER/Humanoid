"""Provider pool with retry, backoff, cooldown, and tiered routing."""

import asyncio
import logging
import random
from datetime import datetime, timedelta

from providers.base import Provider, ProviderError, ProviderFatalError

logger = logging.getLogger(__name__)

# Cooldown config
BASE_COOLDOWN_SECONDS = 30
MAX_COOLDOWN_SECONDS = 300
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class ProviderPool:
    """Manages a pool of LLM providers with retry, backoff, and tiered routing.

    Usage:
        pool = ProviderPool(providers=[gemini, stub])
        result = await pool.call("Write an essay about X", tier="premium")
    """

    def __init__(self, providers: list[Provider]):
        if not providers:
            raise ValueError("ProviderPool requires at least one provider")
        self.providers = providers

    def _get_available_providers(self, tier: str = "cheap") -> list[Provider]:
        """Return providers that are available and match the requested tier.

        Falls back to any available provider if no tier match is found.
        """
        now = datetime.utcnow()
        available = []

        for p in self.providers:
            # Skip providers in cooldown
            if p.status.cooldown_until and now < p.status.cooldown_until:
                continue
            # Reset cooldown if expired
            if p.status.cooldown_until and now >= p.status.cooldown_until:
                p.status.cooldown_until = None
                p.status.is_available = True
            if p.status.is_available:
                available.append(p)

        # Prefer tier-matched providers
        tier_matched = [p for p in available if p.tier == tier]
        return tier_matched if tier_matched else available

    def _apply_cooldown(self, provider: Provider) -> None:
        """Put a provider into cooldown after repeated failures."""
        failures = provider.status.consecutive_failures
        cooldown_seconds = min(
            BASE_COOLDOWN_SECONDS * (2 ** (failures - 1)),
            MAX_COOLDOWN_SECONDS,
        )
        provider.status.cooldown_until = datetime.utcnow() + timedelta(
            seconds=cooldown_seconds
        )
        provider.status.is_available = False
        logger.warning(
            "[ProviderPool] %s in cooldown for %ds (failures: %d)",
            provider.name,
            cooldown_seconds,
            failures,
        )

    async def call(self, prompt: str, tier: str = "cheap", **kwargs) -> str:
        """Route a prompt through the provider pool with retry + backoff.

        Args:
            prompt: The prompt to send.
            tier: "cheap" for structured/verification calls, "premium" for drafting.
            **kwargs: Passed through to the provider's complete() method.

        Returns:
            The completion text.

        Raises:
            ProviderError: If all providers and retries are exhausted.
            ProviderFatalError: If a non-retryable error occurs.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            providers = self._get_available_providers(tier)

            if not providers:
                wait = BASE_BACKOFF_SECONDS * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    "[ProviderPool] No providers available, "
                    "waiting %.1fs (attempt %d/%d)",
                    wait,
                    attempt + 1,
                    MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                continue

            for provider in providers:
                try:
                    result = await provider.complete(prompt, **kwargs)
                    return result

                except ProviderFatalError:
                    # Non-retryable — don't try other providers for auth issues
                    raise

                except ProviderError as e:
                    last_error = e
                    logger.warning(
                        "[ProviderPool] %s failed (attempt %d/%d): %s",
                        provider.name,
                        attempt + 1,
                        MAX_RETRIES,
                        str(e),
                    )
                    # Apply cooldown if provider has 3+ consecutive failures
                    if provider.status.consecutive_failures >= 3:
                        self._apply_cooldown(provider)

            # Exponential backoff + jitter between retry rounds
            wait = BASE_BACKOFF_SECONDS * (2**attempt) + random.uniform(0, 1)
            logger.info("[ProviderPool] Backing off %.1fs before retry", wait)
            await asyncio.sleep(wait)

        raise ProviderError(
            f"All providers exhausted after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )
