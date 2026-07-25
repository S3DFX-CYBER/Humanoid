"""Render service — DOCX generation and PDF conversion.

Runs as an isolated container. Accepts structured document data and
produces formatted DOCX/PDF files. No persistent state.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Humanoid Render Service",
    description="Document formatting — DOCX generation and PDF conversion",
    version="0.1.0",
)


class RenderRequest(BaseModel):
    """Input for document rendering."""

    job_id: str
    title: str = "Untitled Document"
    sections: list[dict] = []
    citation_style: str = "apa"
    references: list[dict] = []


@app.get("/health")
async def health():
    return {"status": "ok", "service": "humanoid-render"}


@app.post("/render/docx")
async def render_docx(body: RenderRequest):
    """Generate a formatted DOCX from structured document data. [STUB]

    Will eventually use python-docx to create a submission-ready document
    with title page, headers, TOC, and formatted citations.
    """
    return {
        "status": "stub",
        "job_id": body.job_id,
        "format": "docx",
        "message": "DOCX rendering not implemented yet. "
        f"Would render {len(body.sections)} sections in {body.citation_style} style.",
    }


@app.post("/render/pdf")
async def render_pdf(body: RenderRequest):
    """Convert a DOCX to PDF using headless LibreOffice (soffice). [STUB]

    Will eventually:
    1. Generate the DOCX first (via render_docx logic)
    2. Run `soffice --headless --convert-to pdf` on the DOCX
    3. Return the PDF file
    """
    return {
        "status": "stub",
        "job_id": body.job_id,
        "format": "pdf",
        "message": "PDF conversion not implemented yet. "
        "Requires headless LibreOffice (soffice) in the container.",
    }
