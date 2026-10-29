FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-common \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY render ./render
COPY templates ./templates
RUN pip install --no-cache-dir ".[render]"

RUN useradd --create-home --uid 10003 appuser \
    && mkdir -p /tmp/lo-profile \
    && chown -R appuser:appuser /app /tmp/lo-profile
USER appuser

EXPOSE 8002

CMD ["uvicorn", "render.main:app", "--host", "0.0.0.0", "--port", "8002"]
