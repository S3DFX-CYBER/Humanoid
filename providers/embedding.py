"""Vector embeddings for pgvector source storage."""

import logging
import google.generativeai as genai
from api.config import get_settings

logger = logging.getLogger(__name__)


async def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional text embedding for the given text."""
    # We must output exactly 384 dimensions to match `vector(384)` in schema.sql
    DIMENSIONS = 384

    settings = get_settings()
    api_key = getattr(settings, "gemini_api_key", None)

    if not api_key or api_key == "missing_key":
        logger.warning(
            "[embedding] No Gemini API key provided. Falling back to zero-vector stub."
        )
        return [0.0] * DIMENSIONS

    try:
        genai.configure(api_key=api_key)

        # text-embedding-004 natively supports output_dimensionality
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
            output_dimensionality=DIMENSIONS,
        )
        return result["embedding"]

    except Exception as e:
        logger.error(
            f"[embedding] Gemini embed failed: {e}. Falling back to zero-vector stub."
        )
        return [0.0] * DIMENSIONS
