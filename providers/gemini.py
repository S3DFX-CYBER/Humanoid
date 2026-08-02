"""Gemini Flash provider implementation."""

import google.generativeai as genai
from providers.base import Provider, ProviderError, ProviderFatalError


class GeminiProvider(Provider):
    """Calls Google Gemini Flash via the generativeai SDK."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        tier: str = "cheap",
    ):
        super().__init__(name="gemini-flash", tier=tier)
        self.api_key = api_key
        self.model_name = model
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.model_name)

    async def complete(self, prompt: str, **kwargs) -> str:
        """Generate a completion using Gemini Flash."""
        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=kwargs.get("temperature", 0.7),
                    max_output_tokens=kwargs.get("max_tokens", 4096),
                ),
            )
            self.mark_success()
            return response.text

        except Exception as e:
            error_str = str(e)
            self.mark_failure()

            # Classify as retryable or fatal
            if "429" in error_str or "Resource exhausted" in error_str:
                raise ProviderError(
                    f"Gemini rate limited: {error_str}", status_code=429
                )
            elif "500" in error_str or "503" in error_str:
                raise ProviderError(
                    f"Gemini server error: {error_str}", status_code=500
                )
            elif "403" in error_str or "401" in error_str:
                raise ProviderFatalError(f"Gemini auth error: {error_str}")
            else:
                raise ProviderError(f"Gemini error: {error_str}")
