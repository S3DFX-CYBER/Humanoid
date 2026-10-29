"""OpenAI provider implementation."""

import logging

from openai import AsyncOpenAI

from providers.base import Provider, ProviderError, ProviderFatalError

logger = logging.getLogger(__name__)

FATAL_MARKERS = ("401", "403", "invalid_api_key", "insufficient_quota")
RATE_MARKERS = ("429", "rate limit")


class OpenAIProvider(Provider):
    """OpenAI chat-completions provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        tier: str = "cheap",
    ):
        super().__init__(name="openai", tier=tier)
        if not api_key:
            raise ValueError("OpenAIProvider requires an api_key")
        self.model_name = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=90.0, max_retries=0)

    async def complete(self, prompt: str, **kwargs) -> str:
        """Generate a plain-text completion."""
        return await self._generate(prompt, json_mode=False, **kwargs)

    async def complete_json(self, prompt: str, **kwargs) -> str:
        """Generate a JSON-mode completion."""
        return await self._generate(prompt, json_mode=True, **kwargs)

    async def _generate(self, prompt: str, json_mode: bool, **kwargs) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=kwargs.get("model", self.model_name),
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.4 if json_mode else 0.7),
                max_tokens=kwargs.get("max_tokens", 8192),
                response_format=(
                    {"type": "json_object"} if json_mode else {"type": "text"}
                ),
            )
        except Exception as exc:
            message = str(exc)
            self.mark_failure(message)
            lowered = message.lower()
            if any(marker in lowered for marker in FATAL_MARKERS):
                raise ProviderFatalError(f"OpenAI auth error: {message}") from exc
            status_code = 429 if any(m in lowered for m in RATE_MARKERS) else None
            raise ProviderError(
                f"OpenAI error: {message}", status_code=status_code
            ) from exc

        if not response.choices:
            self.mark_failure("no choices")
            raise ProviderError("OpenAI returned no completions")

        content = response.choices[0].message.content or ""
        if not content.strip():
            self.mark_failure("empty content")
            raise ProviderError("OpenAI returned an empty completion")

        self.mark_success()
        return content
