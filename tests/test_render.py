"""Tests for the render service document builder."""

from docx import Document

from render.main import RenderRequest, Section, Reference, _build_docx


def _request(**overrides) -> RenderRequest:
    payload = {
        "job_id": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
        "title": "Transformer Architectures",
        "sections": [
            Section(header="Introduction", body="First paragraph.\n\nSecond one."),
            Section(header="Conclusion", body="Closing paragraph."),
        ],
        "references": [
            Reference(
                id="1", title="Attention Is All You Need", url="https://x.example"
            )
        ],
    }
    payload.update(overrides)
    return RenderRequest(**payload)


def _all_text(doc: Document) -> str:
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def test_title_sections_and_references_are_rendered():
    text = _all_text(_build_docx(_request()))

    assert "Transformer Architectures" in text
    assert "Introduction" in text
    assert "Second one." in text
    assert "References" in text
    assert "[1] Attention Is All You Need" in text


def test_reference_url_is_included():
    text = _all_text(_build_docx(_request()))
    assert "https://x.example" in text


def test_leftover_cite_tags_are_stripped():
    request = _request(
        sections=[Section(header="Intro", body="Claim [cite: abc-123] here.")]
    )
    text = _all_text(_build_docx(request))
    assert "[cite" not in text
    assert "Claim  here." in text


def test_document_without_sections_still_builds():
    text = _all_text(_build_docx(_request(sections=[])))
    assert "Transformer Architectures" in text


def test_template_controls_line_spacing():
    doc = _build_docx(_request())
    assert doc.styles["Normal"].paragraph_format.line_spacing == 2.0
