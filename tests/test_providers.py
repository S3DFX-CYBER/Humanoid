"""Tests for provider pool fallback, cooldown, and tier routing."""

import pytest

from providers.base import (
    Provider,
    ProviderError,
    ProviderExhaustedError,
    ProviderFatalError,
)
from providers.pool import ProviderPool


class MockProvider(Provider):
    """Deterministic stand-in for a real provider."""

    def __init__(self, name: str, tier: str = "cheap", failures: int = 0):
        super().__init__(name, tier=tier)
        self.remaining_failures = failures
        self.calls = 0
        self.fatal = False

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        if self.fatal:
            self.mark_failure("bad key")
            raise ProviderFatalError("bad key")
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            self.mark_failure("429")
            raise ProviderError("rate limited", status_code=429)
        self.mark_success()
        return f"{self.name}:{prompt}"


def test_pool_requires_a_provider():
    with pytest.raises(ValueError):
        ProviderPool(providers=[])


async def test_call_returns_first_success():
    primary = MockProvider("primary")
    pool = ProviderPool(providers=[primary])

    assert await pool.call("hello") == "primary:hello"
    assert primary.calls == 1


async def test_failing_provider_falls_through_to_next():
    broken = MockProvider("broken", failures=99)
    healthy = MockProvider("healthy")
    pool = ProviderPool(providers=[broken, healthy])

    assert await pool.call("hello") == "healthy:hello"
    assert broken.calls >= 1
    assert healthy.calls == 1


async def test_exhaustion_raises():
    first = MockProvider("a", failures=99)
    second = MockProvider("b", failures=99)
    pool = ProviderPool(providers=[first, second])

    with pytest.raises(ProviderExhaustedError):
        await pool.call("hello")


async def test_fatal_error_parks_provider_and_tries_the_rest():
    dead = MockProvider("dead")
    dead.fatal = True
    healthy = MockProvider("healthy")
    pool = ProviderPool(providers=[dead, healthy])

    assert await pool.call("hello") == "healthy:hello"
    assert dead.status.is_available is False
    assert dead.status.cooldown_until is not None


async def test_all_fatal_raises_fatal_error():
    first = MockProvider("a")
    first.fatal = True
    pool = ProviderPool(providers=[first])

    with pytest.raises(ProviderFatalError):
        await pool.call("hello")


async def test_tier_preference_is_honoured():
    premium = MockProvider("premium", tier="premium")
    cheap = MockProvider("cheap", tier="cheap")
    pool = ProviderPool(providers=[cheap, premium])

    assert await pool.call("hi", tier="premium") == "premium:hi"
    assert await pool.call("hi", tier="cheap") == "cheap:hi"


async def test_tier_falls_back_when_preferred_tier_is_parked():
    premium = MockProvider("premium", tier="premium")
    premium.status.is_available = False
    cheap = MockProvider("cheap", tier="cheap")
    pool = ProviderPool(providers=[cheap, premium])

    assert await pool.call("hi", tier="premium") == "cheap:hi"
