"""Pipeline stage handlers.

Research, outline, draft, verify, style, and format jobs by reading and
writing stage outputs.  The core research/draft/verify stages perform
real provider-backed work.  Style applies LLM-driven clarity rules
(PRD 6.3a).  Format compiles Markdown and delegates to the render
micro-service for DOCX/PDF.

Stage order:
  researching → outlining → drafting → verifying → styling → formatting
"""

import json
import logging
import re
import uuid

import httpx

from api.config import get_settings
from api.database import set_rls_context
from providers.embedding import generate_embedding
from providers.search import get_search_results, fetch_and_extract_text

logger = logging.getLogger(__name__)


# ── Stage 1: Research ──────────────────────────────────────────


async def run_research(job_id: str, input_data: dict) -> dict:
    """Research sources for the given topic."""
    logger.info("[stage:research] job=%s — beginning real search", job_id)

    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]

    # 1. Fetch job topic & user_id
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id)
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")
        topic = job["topic"]
        user_id = job["user_id"]

    # 2. Generate search queries via LLM
    search_prompt = (
        f"You are an expert researcher. The user's topic is: '{topic}'.\n"
        "Generate 2 highly specific, distinct web search queries to find "
        "the most credible, authoritative information about this topic.\n"
        'Output ONLY a JSON array of strings. Example: ["query 1", "query 2"]'
    )

    try:
        queries_json = await provider_pool.call(search_prompt, tier="cheap")
        queries_json = queries_json.replace("```json", "").replace("```", "").strip()
        queries = json.loads(queries_json)
        if not isinstance(queries, list):
            queries = [topic]
    except Exception as e:
        logger.error("[stage:research] Failed to generate queries: %s", e)
        queries = [topic]

    queries = queries[:2]

    # 3. Execute searches & fetch content
    sources_saved = 0
    for q in queries:
        results = await get_search_results(q, max_results=2)
        for res in results:
            url = res.get("href")
            if not isinstance(url, str) or not url:
                continue

            title = res.get("title", "Untitled")

            content = await fetch_and_extract_text(url, max_chars=4000)
            if not content:
                content = res.get("body", "")

            if len(content) < 50:
                continue

            # 4. Generate embedding
            vector = await generate_embedding(content)

            # 5. Store with RLS context
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    await set_rls_context(conn, user_id)
                    await conn.execute(
                        """
                        INSERT INTO sources (
                            job_id, url, title, content_text,
                            source_type, embedding
                        )
                        VALUES ($1, $2, $3, $4, 'web', $5::vector)
                        """,
                        uuid.UUID(job_id),
                        url,
                        title,
                        content,
                        vector,
                    )
            sources_saved += 1

    return {
        "queries_used": queries,
        "sources_found": sources_saved,
        "note": f"Completed research for topic: {topic}",
    }


# ── Stage 2: Outline ──────────────────────────────────────────


async def run_outline(job_id: str, input_data: dict) -> dict:
    """Generate thesis + outline using sources from Stage 1."""
    logger.info("[stage:outline] job=%s — generating outline", job_id)

    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]

    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id)
        )

        async with conn.transaction():
            await set_rls_context(conn, job["user_id"])
            sources = await conn.fetch(
                "SELECT title, content_text FROM sources WHERE job_id = $1 LIMIT 5",
                uuid.UUID(job_id),
            )

    topic = job["topic"]

    source_context = ""
    for i, s in enumerate(sources):
        text = s["content_text"][:2000]
        source_context += f"Source {i+1}: {s['title']}\n{text}\n\n"

    prompt = f"""You are an expert researcher writing an academic outline.
Topic: {topic}.
Review the following excerpts from our research phase:

{source_context}

Based off these sources, write a comprehensive outline for an authoritative
article. Return your response STRICTLY as a JSON object with the following
schema, and no markdown formatting or backticks:
{{
  "title": "Proposed Article Title",
  "thesis": "A 1-2 sentence thesis statement",
  "sections": [
     "Introduction: [Hook and background]",
     "Section 1: [Main point]",
     ...,
     "Conclusion: [Summary]"
  ]
}}
"""
    try:
        response_text = await provider_pool.call(prompt, tier="premium")
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        outline_json = json.loads(response_text)
    except Exception as e:
        logger.error("[stage:outline] Failed to parse generated outline: %s", e)
        outline_json = {
            "title": f"Report on {topic}",
            "thesis": topic,
            "sections": ["Introduction", "Main Body", "Conclusion"],
        }

    return outline_json


# ── Stage 3: Draft ─────────────────────────────────────────────


async def run_draft(job_id: str, input_data: dict) -> dict:
    """Draft section-by-section with source-tagged claims.

    If a section fails to draft, it is flagged with ``status: failed``
    instead of silently inserting placeholder text.  Downstream stages
    skip failed sections.
    """
    logger.info("[stage:draft] job=%s — drafting content", job_id)

    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]

    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id)
        )

        async with conn.transaction():
            await set_rls_context(conn, job["user_id"])

            # 1. Fetch outline from previous stage — require approval
            outline_row = await conn.fetchrow(
                """
                SELECT output_data FROM job_stages
                WHERE job_id = $1
                  AND stage_name = 'outlining'
                  AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                uuid.UUID(job_id),
            )
            outline_data = outline_row["output_data"] if outline_row else None
            if isinstance(outline_data, str):
                outline_data = json.loads(outline_data)

            # 2. Fetch all sources for RAG context
            sources = await conn.fetch(
                "SELECT id, title, content_text FROM sources WHERE job_id = $1",
                uuid.UUID(job_id),
            )

    if not outline_data or "sections" not in outline_data:
        raise ValueError("Missing outline data to begin drafting")

    topic = job["topic"]
    thesis = outline_data.get("thesis", topic)

    # 3. Build source context with IDs for citation tags
    source_context = ""
    for s in sources:
        text = s["content_text"][:1000]
        source_context += f"Source ID: {s['id']}\nTitle: {s['title']}\n{text}\n\n"

    drafted_sections = []
    failed_sections = []

    # 4. Draft section by section
    for section_outline in outline_data["sections"]:
        prompt = f"""You are an advanced academic writer.
Write the following section for an article.
Topic: {topic}
Overall Thesis: {thesis}

Target Section Objective: {section_outline}

Available Research Context:
{source_context}

INSTRUCTIONS:
1. Write 2-3 comprehensive paragraphs based MUST ONLY on the provided
   sources.
2. Whenever you make a factual claim, append a citation tag using the EXACT
   format: [cite: <SOURCE_ID>]. Do not invent facts; only use the Context.
3. Write ONLY the text for the section; do not include the section header.
"""
        try:
            content = await provider_pool.call(prompt, tier="premium")
            drafted_sections.append(
                {
                    "header": section_outline,
                    "content": content.strip(),
                    "status": "ok",
                }
            )
        except Exception as e:
            logger.error(
                "[stage:draft] Failed drafting section %r: %s",
                section_outline,
                e,
            )
            drafted_sections.append(
                {
                    "header": section_outline,
                    "content": "",
                    "status": "failed",
                    "error": str(e),
                }
            )
            failed_sections.append(section_outline)

    result = {
        "sections": drafted_sections,
        "note": f"Drafted {len(drafted_sections)} sections",
    }

    if failed_sections:
        result["partial_failure"] = True
        result["failed_sections"] = failed_sections

    return result


# ── Stage 4: Verify ────────────────────────────────────────────

# Regex to find [cite: UUID] tags
_CITE_PATTERN = re.compile(r"\[cite:\s*([a-f0-9\-]+)\]")


def _extract_claims(content: str) -> list[tuple[str, list[str]]]:
    """Split content into (claim_text, [source_ids]) tuples.

    Instead of naively splitting on '.' (which breaks on abbreviations,
    decimals, etc.), we split on citation-tag boundaries.  Each chunk of
    text ending with one or more ``[cite: UUID]`` tags is treated as a
    single claim.
    """
    claims: list[tuple[str, list[str]]] = []

    # Split around citation tags, keeping the tags as separate tokens
    parts = _CITE_PATTERN.split(content)

    # parts alternates: [text, uuid, text, uuid, ...]
    # Walk through collecting text + the UUID(s) that follow it.
    current_text = ""
    current_ids: list[str] = []

    for i, part in enumerate(parts):
        if i % 2 == 0:
            # This is a text segment
            if current_ids:
                # We already collected IDs for the previous text — flush
                claims.append((current_text.strip(), current_ids))
                current_text = ""
                current_ids = []
            current_text += part
        else:
            # This is a captured UUID from the citation tag
            current_ids.append(part)

    # Flush any remaining text+ids
    if current_ids and current_text.strip():
        claims.append((current_text.strip(), current_ids))

    return claims


async def run_verify(job_id: str, input_data: dict) -> dict:
    """Verify each claim against its cited source."""
    logger.info("[stage:verify] job=%s — beginning verification", job_id)

    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]

    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id)
        )

        async with conn.transaction():
            await set_rls_context(conn, job["user_id"])

            draft_row = await conn.fetchrow(
                """
                SELECT output_data FROM job_stages
                WHERE job_id = $1
                  AND stage_name = 'drafting'
                  AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                uuid.UUID(job_id),
            )
            draft_data = draft_row["output_data"] if draft_row else None
            if isinstance(draft_data, str):
                draft_data = json.loads(draft_data)

            sources_records = await conn.fetch(
                "SELECT id, title, content_text FROM sources WHERE job_id = $1",
                uuid.UUID(job_id),
            )

    if not draft_data or "sections" not in draft_data:
        raise ValueError("Missing drafted sections data to verify")

    source_map = {str(s["id"]): s for s in sources_records}

    verified_claims = 0
    verification_results = []

    for section in draft_data["sections"]:
        # Skip sections that failed during drafting
        if section.get("status") == "failed":
            continue

        content = section.get("content", "")
        claims = _extract_claims(content)

        for claim_text, source_ids in claims:
            for source_id in source_ids:
                if source_id not in source_map:
                    continue  # orphaned citation

                source_text = source_map[source_id]["content_text"][:2000]

                verify_prompt = f"""You are a fact checker.
Verify the following claim against the provided source.
Claim: "{claim_text}"
Source Text: "{source_text}"

Does the source support the claim?
Return ONLY 'pass', 'unsupported', or 'contradicted'."""

                try:
                    verdict = (
                        (await provider_pool.call(verify_prompt, tier="cheap"))
                        .strip()
                        .lower()
                    )
                    if verdict not in ("pass", "unsupported", "contradicted"):
                        verdict = "unsupported"

                    verification_results.append(
                        {
                            "job_id": job_id,
                            "source_id": source_id,
                            "claim_text": claim_text,
                            "verdict": verdict,
                        }
                    )
                    verified_claims += 1
                except Exception as e:
                    logger.warning("[stage:verify] Verification call failed: %s", e)

    # Bulk insert verification results
    if verification_results:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await set_rls_context(conn, job["user_id"])
                for r in verification_results:
                    await conn.execute(
                        """
                        INSERT INTO verification_results (
                            job_id, source_id, claim_text, verdict
                        )
                        VALUES ($1, $2, $3, $4)
                        """,
                        uuid.UUID(r["job_id"]),
                        uuid.UUID(r["source_id"]),
                        r["claim_text"],
                        r["verdict"],
                    )

    return {
        "verified_claims_count": verified_claims,
        "results": verification_results,
        "note": f"Verified {verified_claims} claims",
    }


# ── Stage 5: Style ─────────────────────────────────────────────

_STYLE_PROMPT_TEMPLATE = """You are an expert academic editor.
Rewrite the following section to improve clarity and academic tone.

RULES (PRD 6.3a):
1. Cut filler words and phrases ("it is important to note that", "basically",
   "in order to", "the fact that", "it should be noted").
2. Fix vague attributions — replace "studies show", "experts say",
   "research suggests" with either a concrete reference or remove the claim.
3. Reduce inflated phrasing — prefer shorter, direct alternatives.
4. Tighten passive voice where an active form is clearer.
5. PRESERVE all [cite: <ID>] tags exactly as they appear — do not remove,
   reorder, or modify any citation tags.
6. Do NOT add new claims or information.  Only rephrase existing text.

SECTION HEADER: {header}
ORIGINAL TEXT:
{content}

Return ONLY the rewritten section text (no header, no commentary)."""


async def run_style(job_id: str, input_data: dict) -> dict:
    """Style & clarity pass using LLM (PRD 6.3a rules)."""
    logger.info("[stage:style] job=%s — styling pass", job_id)

    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]

    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT user_id FROM jobs WHERE id = $1", uuid.UUID(job_id)
        )

        async with conn.transaction():
            await set_rls_context(conn, job["user_id"])
            draft_row = await conn.fetchrow(
                """
                SELECT output_data FROM job_stages
                WHERE job_id = $1
                  AND stage_name = 'drafting'
                  AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                uuid.UUID(job_id),
            )

    draft_data = draft_row["output_data"] if draft_row else None
    if isinstance(draft_data, str):
        draft_data = json.loads(draft_data)

    if not draft_data or "sections" not in draft_data:
        raise ValueError("Missing drafted sections data to style")

    cleaned_sections = []
    edits_made = 0

    for section in draft_data["sections"]:
        # Pass through failed sections untouched
        if section.get("status") == "failed":
            cleaned_sections.append(section)
            continue

        header = section.get("header", "")
        content = section.get("content", "")

        if not content.strip():
            cleaned_sections.append(section)
            continue

        prompt = _STYLE_PROMPT_TEMPLATE.format(header=header, content=content)

        try:
            styled = await provider_pool.call(prompt, tier="cheap")
            styled = styled.strip()
            if styled:
                edits_made += 1
                cleaned_sections.append(
                    {
                        "header": header,
                        "content": styled,
                        "status": section.get("status", "ok"),
                    }
                )
            else:
                # LLM returned empty — keep original
                cleaned_sections.append(section)
        except Exception as e:
            logger.warning(
                "[stage:style] Style rewrite failed for %r, keeping original: %s",
                header,
                e,
            )
            cleaned_sections.append(section)

    return {
        "sections": cleaned_sections,
        "edits_made": edits_made,
        "note": f"Styled {edits_made} sections",
    }


# ── Stage 6: Format ────────────────────────────────────────────


async def run_format(job_id: str, input_data: dict) -> dict:
    """Format into submission-ready document.

    Compiles Markdown from styled sections, then calls the render
    micro-service to produce DOCX (and optionally PDF).  Falls back
    to markdown-only if the render service is unavailable.
    """
    logger.info("[stage:format] job=%s — formatting final document", job_id)

    db_pool = input_data["db_pool"]

    async with db_pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT topic, user_id, citation_style FROM jobs WHERE id = $1",
            uuid.UUID(job_id),
        )

        async with conn.transaction():
            await set_rls_context(conn, job["user_id"])

            style_row = await conn.fetchrow(
                """
                SELECT output_data FROM job_stages
                WHERE job_id = $1
                  AND stage_name = 'styling'
                  AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                uuid.UUID(job_id),
            )

            # Gather source references for the bibliography
            sources = await conn.fetch(
                "SELECT id, title, url FROM sources WHERE job_id = $1",
                uuid.UUID(job_id),
            )

    style_data = style_row["output_data"] if style_row else None
    if isinstance(style_data, str):
        style_data = json.loads(style_data)

    if not style_data or "sections" not in style_data:
        raise ValueError("Missing styled sections data to format")

    topic = job["topic"]
    citation_style = job.get("citation_style", "apa") or "apa"

    # --- Compile Markdown ---
    markdown_doc = f"# {topic.title()}\n\n"

    for section in style_data["sections"]:
        if section.get("status") == "failed":
            continue
        markdown_doc += f"## {section['header']}\n\n"
        markdown_doc += f"{section['content']}\n\n"

    logger.info(
        "[stage:format] Markdown document compiled (%d bytes)", len(markdown_doc)
    )

    # --- Build render request payload ---
    render_sections = [
        {"header": s["header"], "body": s.get("content", "")}
        for s in style_data["sections"]
        if s.get("status") != "failed"
    ]
    references = [
        {"id": str(s["id"]), "title": s["title"], "url": s["url"]}
        for s in sources
    ]

    render_payload = {
        "job_id": job_id,
        "title": topic.title(),
        "sections": render_sections,
        "citation_style": citation_style,
        "references": references,
    }

    # --- Call render micro-service ---
    settings = get_settings()
    render_url = getattr(settings, "render_service_url", "http://render:8002")
    document_url = None
    render_status = "skipped"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{render_url}/render/docx", json=render_payload)
            resp.raise_for_status()
            render_result = resp.json()
            document_url = render_result.get("document_url")
            render_status = render_result.get("status", "ok")
            logger.info(
                "[stage:format] Render service returned status=%s url=%s",
                render_status,
                document_url,
            )
    except Exception as e:
        logger.warning(
            "[stage:format] Render service unavailable, falling back to "
            "markdown-only: %s",
            e,
        )
        render_status = "fallback_markdown"

    return {
        "markdown": markdown_doc,
        "document_url": document_url,
        "render_status": render_status,
        "note": "Compiled into markdown"
        + (" + DOCX" if document_url else " (render unavailable)"),
    }
