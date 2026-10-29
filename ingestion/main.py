"""Ingestion service — file parsing and text extraction.

Runs as an isolated container. Accepts uploaded files and returns extracted
text. No database, no Redis, minimal network egress.
"""

import logging

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ingestion.parsers import extract_text

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

EXTENSION_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "ppt",
    ".ppt": "ppt",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".tif": "image",
    ".bmp": "image",
    ".webp": "image",
}

app = FastAPI(
    title="Humanoid Ingestion Service",
    description="File parsing and text extraction for uploaded documents",
    version="0.3.0",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    logger.exception("[ingestion] unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Extraction failed"})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "humanoid-ingestion"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    """Extract text from an uploaded file (PDF, DOCX, PPTX, or image)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = (
        "." + file.filename.rsplit(".", 1)[-1].lower()
        if "." in file.filename
        else ""
    )
    file_type = EXTENSION_MAP.get(suffix)
    if file_type is None:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix or file.filename}'. "
                "Supported: PDF, DOCX, PPTX, PNG, JPG, TIFF, BMP, WEBP."
            ),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    try:
        text = await extract_text(content, file_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "filename": file.filename,
        "file_type": file_type,
        "text": text,
        "char_count": len(text),
    }
