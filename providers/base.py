"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow() is deprecated)."""
    return datetime.now(timezone.utc)


@dataclass
class ProviderStatus:
    """Tracks the health/cooldown state of a provider."""

    name: str
    is_available: bool = True
    consecutive_failures: int = 0
    last_failure_time: datetime | None = None
    cooldown_until: datetime | None = None
    last_error: str | None = None
    calls: int = 0
    failures: int = 0
    extra: dict = field(default_factory=dict)


class Provider(ABC):
    """Base class for LLM providers."""

    def __init__(self, name: str, tier: str = "cheap"):
        self.name = name
        self.tier = tier  # "cheap" or "premium"
        self.status = ProviderStatus(name=name)

    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str:
        """Send a prompt and return the completion text.

        Raises:
            ProviderError: On retryable errors (429, 5xx).
            ProviderFatalError: On non-retryable errors (auth, bad request).
        """

    async def complete_json(self, prompt: str, **kwargs) -> str:
        """Request a JSON-shaped completion.

        Providers that support native JSON mode override this; the default
        keeps the same contract so callers need not care.
        """
        return await self.complete(prompt, **kwargs)

    def mark_success(self) -> None:
        """Reset failure tracking after a successful call."""
        self.status.consecutive_failures = 0
        self.status.is_available = True
        self.status.cooldown_until = None
        self.status.calls += 1

    def mark_failure(self, error: str | None = None) -> None:
        """Record a failure and potentially trigger cooldown."""
        self.status.consecutive_failures += 1
        self.status.failures += 1
        self.status.last_failure_time = utcnow()
        if error:
            self.status.last_error = error


class ProviderError(Exception):
    """Retryable provider error (429, 5xx, timeouts)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderFatalError(Exception):
    """Non-retryable provider error (auth failure, bad request)."""


class ProviderExhaustedError(ProviderError):
    """Every provider in the pool failed."""
