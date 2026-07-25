"""Stub fallback provider — returns canned responses for dev/testing."""

import logging
from providers.base import Provider

logger = logging.getLogger(__name__)


class StubProvider(Provider):
    """Fallback provider that returns placeholder text.

    Used when no real fallback provider account is configured.
    All calls are logged as stubs so they're visible in monitoring.
    """

    def __init__(self):
        super().__init__(name="stub-fallback", tier="cheap")

    async def complete(self, prompt: str, **kwargs) -> str:
        """Return a canned stub response."""
        logger.warning(
            "[StubProvider] Serving stub response — no real fallback provider configured. "
            "Prompt length: %d chars",
            len(prompt),
        )
        self.mark_success()
        return (
            "[STUB RESPONSE] This is a placeholder from the fallback stub provider. "
            "Configure a real secondary provider to get actual completions. "
            f"Original prompt was {len(prompt)} characters."
        )
