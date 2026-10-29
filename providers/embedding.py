"""Vector embeddings for pgvector source storage."""

import logging

from google import genai
from google.genai import types

from api.config import get_settings

logger = logging.getLogger(__name__)


async def generate_embedding(text: str) -> list[float] | None:
    """Generate an embedding for ``text``, or ``None`` if unavailable.

    Returning ``None`` (and storing SQL NULL) is deliberate: a zero-vector
    fallback makes every source look identical to a similarity search, which
    silently corrupts retrieval instead of failing visibly.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        logger.warning(
            "[embedding] GEMINI_API_KEY is not set — storing sources without "
            "embeddings. Semantic search will be unavailable for this job."
        )
        return None

    trimmed = text[:8000]

    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.embed_content(
            model=settings.embedding_model,
            contents=trimmed,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=settings.embedding_dimensions,
            ),
        )
    except Exception as exc:
        logger.error("[embedding] Gemini embed failed: %s", exc)
        return None

    embeddings = getattr(response, "embeddings", None) or []
    if not embeddings:
        logger.error("[embedding] Gemini returned no embeddings")
        return None

    vector = list(embeddings[0].values or [])
    if len(vector) != settings.embedding_dimensions:
        logger.error(
            "[embedding] expected %d dimensions, got %d — dropping vector",
            settings.embedding_dimensions,
            len(vector),
        )
        return None

    return vector
