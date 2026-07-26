"""File parsers — stubs for Phase 0.

Each parser extracts text from a specific file format.
Real implementations will use pymupdf, python-docx, python-pptx, and
pytesseract respectively. In Phase 0 these return placeholders.
"""

import logging

logger = logging.getLogger(__name__)


async def extract_text(content: bytes, file_type: str) -> str:
    """Route to the appropriate parser based on file type."""
    parsers = {
        "pdf": _parse_pdf,
        "docx": _parse_docx,
        "ppt": _parse_ppt,
        "image": _parse_image_ocr,
    }

    parser = parsers.get(file_type)
    if parser is None:
        raise ValueError(f"No parser for file type: {file_type}")

    return await parser(content)


async def _parse_pdf(content: bytes) -> str:
    """Extract text from PDF using pymupdf. [STUB]"""
    logger.info("[parser:pdf] Stub — %d bytes received", len(content))
    return (
        f"[PDF STUB] Received {len(content)} bytes. "
        "Real extraction not implemented yet."
    )


async def _parse_docx(content: bytes) -> str:
    """Extract text from DOCX using python-docx. [STUB]"""
    logger.info("[parser:docx] Stub — %d bytes received", len(content))
    return (
        f"[DOCX STUB] Received {len(content)} bytes. "
        "Real extraction not implemented yet."
    )


async def _parse_ppt(content: bytes) -> str:
    """Extract text from PPTX using python-pptx. [STUB]"""
    logger.info("[parser:ppt] Stub — %d bytes received", len(content))
    return (
        f"[PPT STUB] Received {len(content)} bytes. "
        "Real extraction not implemented yet."
    )


async def _parse_image_ocr(content: bytes) -> str:
    """Extract text from image using pytesseract OCR. [STUB]

    Note: Genuinely visual content with no extractable text will be
    flagged to the user, not silently guessed at (hard constraint).
    """
    logger.info("[parser:ocr] Stub — %d bytes received", len(content))
    return f"[OCR STUB] Received {len(content)} bytes. Real OCR not implemented yet."
