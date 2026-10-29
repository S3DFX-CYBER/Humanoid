"""Render service — DOCX generation and PDF conversion.

Runs as an isolated container. Accepts structured document data and returns a
finished file. No persistent state, no database access.
"""

import asyncio
import io
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from render.templates import load_template

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Humanoid Render Service",
    description="Document formatting — DOCX generation and PDF conversion",
    version="0.3.0",
)

LEFTOVER_CITE_RE = re.compile(r"\[cite:[^\]]*\]")
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class Section(BaseModel):
    header: str = ""
    body: str = ""


class Reference(BaseModel):
    id: str | None = None
    title: str = "Untitled"
    url: str | None = None


class RenderRequest(BaseModel):
    """Input for document rendering."""

    job_id: str
    title: str = "Untitled Document"
    sections: list[Section] = Field(default_factory=list)
    citation_style: str = "apa"
    references: list[Reference] = Field(default_factory=list)
    template: str = "default"


# ── DOCX helpers ──────────────────────────────────────────────


def _inches(value) -> Inches:
    """Accept 1, "1", "1in", "2.54cm", or "72pt" from a template."""
    if isinstance(value, (int, float)):
        return Inches(float(value))

    text = str(value).strip().lower()
    units = (
        ("in", 1.0),
        ("cm", 1 / 2.54),
        ("pt", 1 / 72),
        ("mm", 1 / 25.4),
    )
    for suffix, factor in units:
        if text.endswith(suffix):
            try:
                return Inches(float(text[: -len(suffix)]) * factor)
            except ValueError:
                break
    try:
        return Inches(float(text))
    except ValueError:
        logger.warning("[render] unreadable margin %r, using 1in", value)
        return Inches(1)


def _set_cell_or_run_font(run, name: str, size_pt: float | None = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size_pt:
        run.font.size = Pt(size_pt)


def _add_page_number(paragraph) -> None:
    """Insert a PAGE field into a header/footer paragraph."""
    run = paragraph.add_run()
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = "PAGE"
    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_begin)
    run._r.append(instr_text)
    run._r.append(fld_char_end)


def _build_docx(body: RenderRequest) -> Document:
    """Build a python-docx Document from structured data and a template."""
    template = load_template(body.template)
    fonts = template["fonts"]
    spacing = template["spacing"]
    margins = template["page"]["margins"]

    doc = Document()

    for section in doc.sections:
        section.top_margin = _inches(margins.get("top", 1))
        section.bottom_margin = _inches(margins.get("bottom", 1))
        section.left_margin = _inches(margins.get("left", 1))
        section.right_margin = _inches(margins.get("right", 1))

    normal = doc.styles["Normal"]
    normal.font.name = fonts["body"]
    normal.font.size = Pt(float(fonts["bodySize"]))
    normal.paragraph_format.line_spacing = float(spacing.get("lineSpacing", 2.0))
    normal.paragraph_format.space_after = Pt(
        float(spacing.get("paragraphSpacing", 0))
    )

    for level in (1, 2, 3):
        try:
            heading_style = doc.styles[f"Heading {level}"]
        except KeyError:  # pragma: no cover - python-docx always ships these
            continue
        heading_style.font.name = fonts["heading"]
        heading_style.font.size = Pt(float(fonts["headingSize"]))
        heading_style.font.color.rgb = None

    if template["headers"].get("enabled"):
        header_para = doc.sections[0].header.paragraphs[0]
        header_para.text = body.title
        header_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if template["headers"].get("includePageNumber"):
            header_para.add_run("\t")
            _add_page_number(header_para)

    # -- Title page --
    if template["titlePage"].get("enabled", True):
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_para.paragraph_format.space_before = Pt(120)
        run = title_para.add_run(body.title)
        run.bold = True
        run.font.size = Pt(float(fonts["headingSize"]) + 8)
        _set_cell_or_run_font(run, fonts["heading"])
        doc.add_page_break()
    else:
        heading = doc.add_heading(body.title, level=1)
        _set_cell_or_run_font(heading.runs[0], fonts["heading"])

    # -- Contents (static, so it survives PDF conversion) --
    printable = [s for s in body.sections if s.body.strip()]
    if template["toc"].get("enabled") and len(printable) > 1:
        doc.add_heading("Contents", level=1)
        for section in printable:
            entry = doc.add_paragraph()
            entry.paragraph_format.left_indent = Inches(0.25)
            entry.paragraph_format.space_after = Pt(2)
            entry.add_run(section.header or "Untitled section")
        doc.add_page_break()

    # -- Sections --
    for section in printable:
        heading = doc.add_heading(section.header or "Untitled section", level=2)
        if heading.runs:
            _set_cell_or_run_font(heading.runs[0], fonts["heading"])

        cleaned = LEFTOVER_CITE_RE.sub("", section.body)
        for paragraph_text in [p.strip() for p in cleaned.split("\n\n") if p.strip()]:
            paragraph = doc.add_paragraph(paragraph_text)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # -- References --
    if body.references:
        doc.add_page_break()
        doc.add_heading("References", level=1)
        for index, ref in enumerate(body.references, 1):
            text = f"[{index}] {ref.title or 'Untitled'}"
            if ref.url:
                text += f". {ref.url}"
            paragraph = doc.add_paragraph(text)
            paragraph.paragraph_format.left_indent = Inches(0.5)
            paragraph.paragraph_format.first_line_indent = Inches(-0.5)

    return doc


def _convert_to_pdf(docx_path: Path, outdir: Path) -> subprocess.CompletedProcess:
    """Blocking LibreOffice conversion — run in a thread."""
    return subprocess.run(
        [
            "soffice",
            "--headless",
            "--norestore",
            "-env:UserInstallation=file:///tmp/lo-profile",
            "--convert-to",
            "pdf",
            "--outdir",
            str(outdir),
            str(docx_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env={"HOME": "/tmp", "PATH": "/usr/local/bin:/usr/bin:/bin"},
    )


# ── Routes ────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "humanoid-render"}


@app.post("/render/docx")
async def render_docx(body: RenderRequest):
    """Generate a formatted DOCX and return it as a download."""
    try:
        doc = await asyncio.to_thread(_build_docx, body)
    except Exception as exc:
        logger.exception("[render] DOCX build failed")
        raise HTTPException(status_code=500, detail=f"DOCX build failed: {exc}")

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    filename = f"humanoid_{body.job_id[:8]}.docx"
    return StreamingResponse(
        buffer,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/render/pdf")
async def render_pdf(body: RenderRequest):
    """Convert the DOCX to PDF via headless LibreOffice."""
    try:
        doc = await asyncio.to_thread(_build_docx, body)
    except Exception as exc:
        logger.exception("[render] DOCX build failed")
        raise HTTPException(status_code=500, detail=f"DOCX build failed: {exc}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        docx_path = tmp / "document.docx"
        doc.save(str(docx_path))

        try:
            result = await asyncio.to_thread(_convert_to_pdf, docx_path, tmp)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(
                status_code=504, detail="PDF conversion timed out"
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503, detail="LibreOffice is not installed"
            ) from exc

        if result.returncode != 0:
            logger.error("[render] soffice failed: %s", result.stderr)
            raise HTTPException(
                status_code=500,
                detail=f"PDF conversion failed: {result.stderr[:500]}",
            )

        pdf_path = tmp / "document.pdf"
        if not pdf_path.exists():
            raise HTTPException(
                status_code=500, detail="PDF was not produced by the converter"
            )
        pdf_bytes = pdf_path.read_bytes()

    filename = f"humanoid_{body.job_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
