FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tesseract for OCR. libgl1-mesa-glx no longer exists in Debian 12 — the
# current package names are libgl1 and libglx-mesa0.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglx-mesa0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY ingestion ./ingestion
RUN pip install --no-cache-dir ".[ingestion]"

RUN useradd --create-home --uid 10002 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

CMD ["uvicorn", "ingestion.main:app", "--host", "0.0.0.0", "--port", "8001"]
