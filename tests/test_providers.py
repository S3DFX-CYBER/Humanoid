"""Tests for provider pool fallback and cooldown logic."""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone

from providers.base import Provider, ProviderStatus
from providers.pool import ProviderPool, ProviderExhaustedError

class MockProvider(Provider):
    def __init__(self, name: str, should_fail: bool = False, delay: float = 0):
        super().__init__(name)
        self.should_fail = should_fail
        self.delay = delay
        self.calls = 0

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
            
        if self.should_fail:
            raise Exception("Mock provider simulated failure")
            
        return f"{self.name} output for: {prompt}"

@pytest.mark.asyncio
async def test_provider_pool_success():
    pool = ProviderPool()
    # Mocking out the real providers for tests
    pool.providers["cheap"] = [MockProvider("mock_cheap")]
    
    result = await pool.call("test prompt", tier="cheap")
    assert result == "mock_cheap output for: test prompt"
    assert pool.providers["cheap"][0].calls == 1

@pytest.mark.asyncio
async def test_provider_pool_fallback():
    pool = ProviderPool()
    primary = MockProvider("primary", should_fail=True)
    fallback = MockProvider("fallback", should_fail=False)
    
    pool.providers["cheap"] = [primary, fallback]
    
    result = await pool.call("test prompt", tier="cheap")
    
    # Primary should be called up to MAX_RETRIES (3)
    assert primary.calls == 3
    # It should then fall back to the secondary
    assert result == "fallback output for: test prompt"
    assert fallback.calls == 1
    
    # Primary should now be in cooldown
    status = pool.status[primary.name]
    assert status.is_available is False
    assert status.cooldown_until is not None
    assert status.cooldown_until > datetime.now(timezone.utc)

@pytest.mark.asyncio
async def test_provider_pool_exhaustion():
    pool = ProviderPool()
    primary = MockProvider("primary", should_fail=True)
    fallback = MockProvider("fallback", should_fail=True)
    
    pool.providers["cheap"] = [primary, fallback]
    
    with pytest.raises(ProviderExhaustedError):
        await pool.call("test prompt", tier="cheap")
        
    assert primary.calls == 3
    assert fallback.calls == 3
