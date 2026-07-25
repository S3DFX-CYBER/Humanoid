FROM python:3.12-slim

WORKDIR /app

# System deps for file parsing (Phase 0 stubs don't need these yet,
# but the container is ready for real parsers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[ingestion]"

COPY ingestion/ ./ingestion/

# Ingestion service runs on port 8001
CMD ["uvicorn", "ingestion.main:app", "--host", "0.0.0.0", "--port", "8001"]
