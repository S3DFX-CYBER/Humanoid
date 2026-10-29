"""Gemini provider implementation (google-genai SDK).

``google.generativeai`` reached end of life; this uses the supported
``google-genai`` client, which also gives us native JSON mode.
"""

import logging

from google import genai
from google.genai import types

from providers.base import Provider, ProviderError, ProviderFatalError

logger = logging.getLogger(__name__)

FATAL_MARKERS = (
    "api key not valid",
    "api_key_invalid",
    "permission denied",
    "unauthenticated",
    "401",
    "403",
)
RATE_MARKERS = ("429", "resource exhausted", "rate limit", "quota")
SERVER_MARKERS = ("500", "503", "504", "unavailable", "internal")


def classify_error(error: str) -> tuple[bool, int | None]:
    """Return (is_retryable, status_code) for a Gemini error string."""
    lowered = error.lower()
    if any(marker in lowered for marker in FATAL_MARKERS):
        return False, 401
    if any(marker in lowered for marker in RATE_MARKERS):
        return True, 429
    if any(marker in lowered for marker in SERVER_MARKERS):
        return True, 503
    return True, None


class GeminiProvider(Provider):
    """Calls Gemini Flash through the google-genai client."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        tier: str = "cheap",
    ):
        super().__init__(name="gemini", tier=tier)
        if not api_key:
            raise ValueError("GeminiProvider requires an api_key")
        self.model_name = model
        self._client = genai.Client(api_key=api_key)

    async def complete(self, prompt: str, **kwargs) -> str:
        """Generate a plain-text completion."""
        return await self._generate(prompt, json_mode=False, **kwargs)

    async def complete_json(self, prompt: str, **kwargs) -> str:
        """Generate a completion constrained to JSON output."""
        return await self._generate(prompt, json_mode=True, **kwargs)

    async def _generate(self, prompt: str, json_mode: bool, **kwargs) -> str:
        config = types.GenerateContentConfig(
            temperature=kwargs.get("temperature", 0.4 if json_mode else 0.7),
            max_output_tokens=kwargs.get("max_tokens", 8192),
            response_mime_type="application/json" if json_mode else None,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # SDK raises a wide variety of types
            message = str(exc)
            self.mark_failure(message)
            retryable, status_code = classify_error(message)
            if not retryable:
                raise ProviderFatalError(f"Gemini auth error: {message}") from exc
            raise ProviderError(
                f"Gemini error: {message}", status_code=status_code
            ) from exc

        text = getattr(response, "text", None)
        if not text:
            self.mark_failure("empty response")
            raise ProviderError("Gemini returned an empty response")

        self.mark_success()
        return text
