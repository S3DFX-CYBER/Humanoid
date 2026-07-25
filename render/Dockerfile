FROM python:3.12-slim

WORKDIR /app

# Install LibreOffice headless for DOCX → PDF conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-common \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[render]"

COPY render/ ./render/

# Render service runs on port 8002
CMD ["uvicorn", "render.main:app", "--host", "0.0.0.0", "--port", "8002"]
