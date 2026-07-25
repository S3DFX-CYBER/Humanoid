"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProviderStatus:
    """Tracks the health/cooldown state of a provider."""
    name: str
    is_available: bool = True
    consecutive_failures: int = 0
    last_failure_time: datetime | None = None
    cooldown_until: datetime | None = None


class Provider(ABC):
    """Base class for LLM providers."""

    def __init__(self, name: str, tier: str = "cheap"):
        self.name = name
        self.tier = tier  # "cheap" or "premium"
        self.status = ProviderStatus(name=name)

    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str:
        """Send a prompt and return the completion text.

        Args:
            prompt: The user/system prompt to complete.
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.)

        Returns:
            The model's response text.

        Raises:
            ProviderError: On retryable errors (429, 5xx).
            ProviderFatalError: On non-retryable errors (auth, bad request).
        """
        ...

    def mark_success(self) -> None:
        """Reset failure tracking after a successful call."""
        self.status.consecutive_failures = 0
        self.status.is_available = True
        self.status.cooldown_until = None

    def mark_failure(self) -> None:
        """Record a failure and potentially trigger cooldown."""
        self.status.consecutive_failures += 1
        self.status.last_failure_time = datetime.utcnow()


class ProviderError(Exception):
    """Retryable provider error (429, 5xx)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderFatalError(Exception):
    """Non-retryable provider error (auth failure, bad request)."""
    pass
