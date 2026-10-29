"""File parsers — PDF, DOCX, PPTX, and image OCR.

Every parser is defensive: a corrupt or hostile file must produce a clean
error, never a crash or an unbounded memory spike. Parsing runs in a worker
thread so the event loop stays responsive.
"""

import asyncio
import io
import logging

logger = logging.getLogger(__name__)

MAX_EXTRACTED_CHARS = 500_000


def _truncate(text: str) -> str:
    if len(text) <= MAX_EXTRACTED_CHARS:
        return text
    logger.warning("[parsers] truncating extraction at %d chars", MAX_EXTRACTED_CHARS)
    return text[:MAX_EXTRACTED_CHARS]


def _parse_pdf_sync(content: bytes) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    with fitz.open(stream=content, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("PDF is password protected")
        for page_number, page in enumerate(document, 1):
            text = page.get_text("text").strip()
            if text:
                parts.append(f"[page {page_number}]\n{text}")
    return _truncate("\n\n".join(parts))


def _parse_docx_sync(content: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(content))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return _truncate("\n".join(parts))


def _parse_ppt_sync(content: bytes) -> str:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(content))
    parts: list[str] = []
    for index, slide in enumerate(presentation.slides, 1):
        slide_parts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    slide_parts.append(text)
        if slide_parts:
            parts.append(f"[slide {index}]\n" + "\n".join(slide_parts))
    return _truncate("\n\n".join(parts))


def _parse_image_sync(content: bytes) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(content)) as image:
        image = image.convert("L")
        text = pytesseract.image_to_string(image)
    return _truncate(text.strip())


PARSERS = {
    "pdf": _parse_pdf_sync,
    "docx": _parse_docx_sync,
    "ppt": _parse_ppt_sync,
    "image": _parse_image_sync,
}


async def extract_text(content: bytes, file_type: str) -> str:
    """Route to the parser for ``file_type`` and return extracted text.

    Raises:
        ValueError: for unsupported types or unreadable files.
    """
    parser = PARSERS.get(file_type)
    if parser is None:
        raise ValueError(f"No parser for file type: {file_type}")

    try:
        text = await asyncio.to_thread(parser, content)
    except ValueError:
        raise
    except ImportError as exc:
        logger.error("[parsers] missing dependency for %s: %s", file_type, exc)
        raise ValueError(
            f"Server is missing the parser dependency for {file_type}"
        ) from exc
    except Exception as exc:
        logger.warning("[parsers] %s parse failed: %s", file_type, exc)
        raise ValueError(f"Could not read this {file_type} file: {exc}") from exc

    if not text.strip():
        raise ValueError(
            "No extractable text found. If this file is a scan or an image of "
            "text, it needs OCR before it can be used as a source."
        )

    return text
