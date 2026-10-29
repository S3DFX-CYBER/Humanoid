"""Stub fallback provider — canned responses for local development only.

Never enabled by default. If this provider answers a drafting call the user
receives placeholder prose, so it is gated behind ``ALLOW_STUB_PROVIDER`` and
always logged loudly.
"""

import logging

from providers.base import Provider

logger = logging.getLogger(__name__)


class StubProvider(Provider):
    """Fallback provider that returns deterministic placeholder text."""

    def __init__(self):
        super().__init__(name="stub", tier="cheap")

    async def complete(self, prompt: str, **kwargs) -> str:
        logger.warning(
            "[StubProvider] serving placeholder response — "
            "no real provider is configured. Prompt length: %d chars",
            len(prompt),
        )
        self.mark_success()
        return (
            "[STUB] No language model is configured, so this is placeholder "
            f"text for a {len(prompt)}-character prompt. Set GEMINI_API_KEY "
            "or OPENAI_API_KEY to generate real content."
        )

    async def complete_json(self, prompt: str, **kwargs) -> str:
        self.mark_success()
        return '{"title": "Stub outline", "thesis": "", "sections": ["Introduction"]}'
