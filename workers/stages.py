"""Pipeline stage handler stubs.

Each stage is an async function that receives the job context and
produces output. In Phase 0 these are no-ops — real logic comes in
later phases.

Stage order:
  researching → outlining → drafting → verifying → styling → formatting
"""

import logging

logger = logging.getLogger(__name__)


async def run_research(job_id: str, input_data: dict) -> dict:
    """Stage 1: Research sources for the given topic.

    Will eventually:
    - Search the web for relevant sources
    - Embed and store source content in pgvector
    - Score source credibility
    """
    logger.info("[stage:research] job=%s — stub execution", job_id)
    return {"sources_found": 0, "note": "stub — no real research yet"}


async def run_outline(job_id: str, input_data: dict) -> dict:
    """Stage 2: Generate thesis + outline.

    Will eventually:
    - Use retrieved sources to propose a thesis
    - Generate a structured outline
    - Wait for user approval before proceeding to drafting
    """
    logger.info("[stage:outline] job=%s — stub execution", job_id)
    return {"outline": [], "note": "stub — no real outline yet"}


async def run_draft(job_id: str, input_data: dict) -> dict:
    """Stage 3: Draft section-by-section with source-tagged claims.

    Will eventually:
    - Draft each section using RAG-constrained generation
    - Tag every factual claim to a specific source ID
    - No claim may be invented without a backing source
    """
    logger.info("[stage:draft] job=%s — stub execution", job_id)
    return {"sections": [], "note": "stub — no real drafting yet"}


async def run_verify(job_id: str, input_data: dict) -> dict:
    """Stage 4: Verify each claim against its cited source.

    Will eventually:
    - Check each claim: PASS / UNSUPPORTED / CONTRADICTED
    - Loop back to redraft flagged sentences/sections
    """
    logger.info("[stage:verify] job=%s — stub execution", job_id)
    return {"verified_claims": 0, "note": "stub — no real verification yet"}


async def run_style(job_id: str, input_data: dict) -> dict:
    """Stage 5: Style & clarity pass.

    Will eventually:
    - Cut filler and vague attribution
    - Replace vague claims with real citations
    - NEVER add new facts
    - NOT tuned toward evading AI-content detectors (hard constraint)
    """
    logger.info("[stage:style] job=%s — stub execution", job_id)
    return {"edits_made": 0, "note": "stub — no real style pass yet"}


async def run_format(job_id: str, input_data: dict) -> dict:
    """Stage 6: Format into submission-ready DOCX + PDF.

    Will eventually:
    - Generate DOCX with title page, headers, TOC, citation style
    - Convert to PDF via headless LibreOffice
    - Produce suggested-edits list (5-10 items)
    """
    logger.info("[stage:format] job=%s — stub execution", job_id)
    return {"document_url": None, "note": "stub — no real formatting yet"}
