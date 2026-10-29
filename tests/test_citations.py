"""Tests for citation numbering and the verification appendix."""

from workers.citations import build_verification_section, number_citations

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
MISSING = "33333333-3333-3333-3333-333333333333"


def _refs():
    return [
        {"id": A, "title": "First source", "url": "https://a.example"},
        {"id": B, "title": "Second source", "url": "https://b.example"},
    ]


def test_tags_become_numbers_in_first_appearance_order():
    sections = [
        {"header": "One", "content": f"Claim one [cite: {B}].", "status": "ok"},
        {"header": "Two", "content": f"Claim two [cite: {A}].", "status": "ok"},
    ]

    numbered, refs, unresolved = number_citations(sections, _refs())

    assert numbered[0]["content"] == "Claim one [1]."
    assert numbered[1]["content"] == "Claim two [2]."
    assert [r["id"] for r in refs] == [B, A]
    assert unresolved == 0


def test_repeated_source_reuses_its_number():
    sections = [
        {"header": "One", "content": f"A [cite: {A}]. B [cite: {A}].", "status": "ok"}
    ]

    numbered, refs, _ = number_citations(sections, _refs())

    assert numbered[0]["content"] == "A [1]. B [1]."
    assert len(refs) == 1


def test_uncited_references_are_dropped():
    sections = [{"header": "One", "content": f"Only A [cite: {A}].", "status": "ok"}]

    _, refs, _ = number_citations(sections, _refs())

    assert len(refs) == 1
    assert refs[0]["id"] == A


def test_unknown_source_id_is_stripped_and_counted():
    sections = [
        {"header": "One", "content": f"Ghost [cite: {MISSING}].", "status": "ok"}
    ]

    numbered, refs, unresolved = number_citations(sections, _refs())

    assert "[cite" not in numbered[0]["content"]
    assert refs == []
    assert unresolved == 1


def test_malformed_tags_never_ship():
    sections = [
        {"header": "One", "content": "Bad [cite: not-a-uuid] tag.", "status": "ok"}
    ]

    numbered, _, _ = number_citations(sections, _refs())

    assert "[cite" not in numbered[0]["content"]


def test_verification_section_lists_only_flagged_claims():
    results = [
        {"claim_text": "Supported claim", "verdict": "pass"},
        {"claim_text": "Dodgy claim", "verdict": "unsupported"},
        {"claim_text": "Wrong claim", "verdict": "contradicted"},
    ]

    section = build_verification_section(results)

    assert section is not None
    assert "UNSUPPORTED" in section["content"]
    assert "CONTRADICTED" in section["content"]
    assert "Supported claim" not in section["content"]


def test_verification_section_is_none_when_everything_passes():
    assert build_verification_section([{"claim_text": "x", "verdict": "pass"}]) is None
