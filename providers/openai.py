"""OpenAI provider implementation."""

import logging
from openai import AsyncOpenAI
from providers.base import Provider
from api.config import get_settings

logger = logging.getLogger(__name__)


class OpenAIProvider(Provider):
    """OpenAI API provider for LLM completion."""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        super().__init__("openai")
        self.model_name = model_name
        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the OpenAI client with API key from settings."""
        settings = get_settings()
        # Fall back to a dummy key and let the client fail naturally.
        api_key = getattr(settings, "openai_api_key", "missing_key")

        try:
            self.client = AsyncOpenAI(api_key=api_key)
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client: {e}")

    async def complete(self, prompt: str, **kwargs) -> str:
        """Generate a completion using OpenAI's chat API."""
        if not self.client:
            raise Exception("OpenAI client not initialized")

        logger.info(f"[openai] Calling completion (model={self.model_name})")

        response = await self.client.chat.completions.create(
            model=kwargs.get("model", self.model_name),
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.7),
        )

        if not response.choices:
            raise Exception("No completions returned from OpenAI")

        return response.choices[0].message.content or ""
