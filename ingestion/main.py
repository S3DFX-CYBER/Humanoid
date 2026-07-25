"""Ingestion service — file parsing and text extraction.

Runs as an isolated container. Accepts uploaded files and returns
extracted text content. No persistent state, minimal network egress.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from ingestion.parsers import extract_text

app = FastAPI(
    title="Humanoid Ingestion Service",
    description="File parsing and text extraction for uploaded documents",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "humanoid-ingestion"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    """Extract text from an uploaded file.

    Supports PDF, DOCX, PPTX, and images (OCR fallback).
    Returns the extracted text and detected file type.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    filename = file.filename.lower()

    # Determine file type from extension
    if filename.endswith(".pdf"):
        file_type = "pdf"
    elif filename.endswith(".docx"):
        file_type = "docx"
    elif filename.endswith((".pptx", ".ppt")):
        file_type = "ppt"
    elif filename.endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp")):
        file_type = "image"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {filename}",
        )

    text = await extract_text(content, file_type)

    return {
        "filename": file.filename,
        "file_type": file_type,
        "text": text,
        "char_count": len(text),
    }
