"""Pipeline stage handlers.

Stage order:
  research -> outline -> draft -> verify -> style -> format

Each handler receives ``(job_id, ctx)`` where ``ctx`` carries the provider
pool, the database pool, and the job owner's ``user_id``.  Every database
access goes through ``user_connection`` so Row-Level Security applies.
"""

import json
import logging
import re
import uuid

import httpx

from api.config import get_settings
from api.database import user_connection
from providers.embedding import generate_embedding
from providers.search import fetch_and_extract_text, get_search_results
from workers.citations import build_verification_section, number_citations

logger = logging.getLogger(__name__)

MAX_SOURCES = 6
MIN_SOURCE_CHARS = 200


# ── Shared helpers ─────────────────────────────────────────────


async def _load_job(conn, job_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT id, topic, user_id, citation_style FROM jobs WHERE id = $1",
        uuid.UUID(job_id),
    )
    if row is None:
        raise ValueError(f"Job {job_id} not found")
    return dict(row)


async def _stage_output(conn, job_id: str, stage_name: str) -> dict | None:
    """Read the most recent completed output for a stage."""
    row = await conn.fetchrow(
        """
        SELECT output_data FROM job_stages
        WHERE job_id = $1 AND stage_name = $2 AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
        """,
        uuid.UUID(job_id),
        stage_name,
    )
    if row is None:
        return None
    data = row["output_data"]
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None
    return data


def _parse_json_response(text: str) -> dict:
    """Parse a JSON response, tolerating stray code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Models sometimes wrap JSON in prose — grab the outermost object.
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


# ── Stage 1: Research ─────────────────────────────────────────


async def run_research(job_id: str, ctx: dict) -> dict:
    """Find sources for the topic and store them with embeddings."""
    provider_pool = ctx["provider_pool"]
    db_pool = ctx["db_pool"]
    user_id = ctx["user_id"]

    async with user_connection(db_pool, user_id) as conn:
        job = await _load_job(conn, job_id)

    topic = job["topic"]
    logger.info("[stage:research] job=%s topic=%r", job_id, topic)

    query_prompt = (
        "You are an expert research librarian.\n"
        f"Topic: {topic}\n"
        "Write 3 specific, complementary web search queries that would find "
        "authoritative sources (peer-reviewed work, primary data, official "
        "documentation) for this topic.\n"
        'Respond as JSON: {"queries": ["query 1", "query 2", "query 3"]}'
    )

    try:
        queries = _parse_json_response(
            await provider_pool.call_json(query_prompt, tier="cheap")
        ).get("queries") or []
    except Exception as exc:
        logger.warning("[stage:research] query generation failed: %s", exc)
        queries = []

    queries = [q for q in queries if isinstance(q, str) and q.strip()][:3]
    if not queries:
        queries = [topic]

    seen_urls: set[str] = set()
    saved = 0
    skipped = 0

    for query in queries:
        if saved >= MAX_SOURCES:
            break
        results = await get_search_results(query, max_results=4)

        for result in results:
            if saved >= MAX_SOURCES:
                break

            url = result["href"]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            content = await fetch_and_extract_text(url, max_chars=6000)
            if len(content) < MIN_SOURCE_CHARS:
                content = result.get("body", "")
            if len(content) < MIN_SOURCE_CHARS:
                skipped += 1
                continue

            vector = await generate_embedding(content)

            async with user_connection(db_pool, user_id) as conn:
                inserted = await conn.fetchval(
                    """
                    INSERT INTO sources (job_id, url, title, content_text,
                                         source_type, embedding)
                    VALUES ($1, $2, $3, $4, 'web', $5::vector)
                    ON CONFLICT (job_id, url) DO NOTHING
                    RETURNING id
                    """,
                    uuid.UUID(job_id),
                    url,
                    result["title"][:500],
                    content,
                    vector,
                )
            if inserted:
                saved += 1

    if saved == 0:
        raise ValueError(
            "No usable sources were found for this topic. Try a more specific "
            "topic, or check that the search provider is reachable."
        )

    return {
        "queries_used": queries,
        "sources_found": saved,
        "sources_skipped": skipped,
        "note": f"Collected {saved} sources for {topic!r}",
    }


# ── Stage 2: Outline ──────────────────────────────────────────


async def run_outline(job_id: str, ctx: dict) -> dict:
    """Generate a title, thesis, and section outline from the sources."""
    provider_pool = ctx["provider_pool"]
    db_pool = ctx["db_pool"]
    user_id = ctx["user_id"]

    async with user_connection(db_pool, user_id) as conn:
        job = await _load_job(conn, job_id)
        sources = await conn.fetch(
            """
            SELECT title, content_text FROM sources
            WHERE job_id = $1
            ORDER BY created_at ASC
            LIMIT 6
            """,
            uuid.UUID(job_id),
        )

    context = ""
    for index, source in enumerate(sources, 1):
        context += (
            f"Source {index}: {source['title']}\n"
            f"{(source['content_text'] or '')[:1800]}\n\n"
        )

    prompt = f"""You are an academic editor planning a research document.

Topic: {job['topic']}

Source excerpts:
{context}

Produce an outline. Respond with JSON only, in exactly this shape:
{{
  "title": "A specific, informative document title",
  "thesis": "One or two sentences stating the document's argument",
  "sections": [
    "Introduction: <what this section establishes>",
    "Section: <main point>",
    "Conclusion: <what this section closes>"
  ]
}}
Use 4 to 6 sections. Every section must be supportable from the excerpts."""

    try:
        outline = _parse_json_response(
            await provider_pool.call_json(prompt, tier="premium")
        )
    except Exception as exc:
        logger.error("[stage:outline] generation failed: %s", exc)
        raise ValueError(f"Could not generate an outline: {exc}") from exc

    sections = outline.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Outline contained no sections")

    return {
        "title": outline.get("title") or job["topic"],
        "thesis": outline.get("thesis") or "",
        "sections": [str(s) for s in sections][:8],
        "sources_used": len(sources),
    }


# ── Stage 3: Draft ────────────────────────────────────────────


async def run_draft(job_id: str, ctx: dict) -> dict:
    """Draft each outline section against the retrieved sources."""
    provider_pool = ctx["provider_pool"]
    db_pool = ctx["db_pool"]
    user_id = ctx["user_id"]

    async with user_connection(db_pool, user_id) as conn:
        job = await _load_job(conn, job_id)
        outline = await _stage_output(conn, job_id, "outline")
        sources = await conn.fetch(
            """
            SELECT id, title, url, content_text FROM sources
            WHERE job_id = $1
            ORDER BY created_at ASC
            """,
            uuid.UUID(job_id),
        )

    if not outline or not outline.get("sections"):
        raise ValueError("Missing outline data to begin drafting")

    context = ""
    for source in sources:
        context += (
            f"SOURCE_ID: {source['id']}\n"
            f"TITLE: {source['title']}\n"
            f"URL: {source['url']}\n"
            f"{(source['content_text'] or '')[:2500]}\n\n"
        )

    thesis = outline.get("thesis") or job["topic"]
    drafted: list[dict] = []
    failed: list[str] = []

    for section in outline["sections"]:
        prompt = f"""You are drafting one section of an academic document.

Document title: {outline.get('title', job['topic'])}
Overall thesis: {thesis}
This section's objective: {section}

Research context (the only information you may use):
{context}

Rules:
1. Write 2-3 paragraphs of clear academic prose.
2. Support every factual claim with a citation tag in the exact form
   [cite: SOURCE_ID] using the SOURCE_ID values above. Never invent a
   SOURCE_ID.
3. If the context does not support a point, omit the point. Do not guess.
4. Output the section body only — no heading, no commentary."""

        try:
            content = (await provider_pool.call(prompt, tier="premium")).strip()
        except Exception as exc:
            logger.error("[stage:draft] section %r failed: %s", section, exc)
            drafted.append(
                {
                    "header": section,
                    "content": "",
                    "status": "failed",
                    "error": str(exc),
                }
            )
            failed.append(section)
            continue

        drafted.append({"header": section, "content": content, "status": "ok"})

    if not any(s["status"] == "ok" for s in drafted):
        raise ValueError("Every section failed to draft — no content produced")

    result: dict = {
        "sections": drafted,
        "note": f"Drafted {len(drafted) - len(failed)}/{len(drafted)} sections",
    }
    if failed:
        result["partial_failure"] = True
        result["failed_sections"] = failed
    return result


# ── Stage 4: Verify ───────────────────────────────────────────

CITE_PATTERN = re.compile(r"\[cite:\s*([0-9a-fA-F-]{36})\s*\]")


def _extract_claims(content: str) -> list[tuple[str, str]]:
    """Split content into (claim_text, source_id) pairs.

    A claim is the run of text preceding a citation tag. Splitting on tag
    boundaries avoids the abbreviation and decimal-point breakage of a
    naive sentence split.
    """
    claims: list[tuple[str, str]] = []
    last_end = 0
    pending = ""

    for match in CITE_PATTERN.finditer(content):
        pending += content[last_end : match.start()]
        claim_text = pending.strip()
        if claim_text:
            claims.append((claim_text, match.group(1).lower()))
        pending = ""
        last_end = match.end()

    return claims


async def run_verify(job_id: str, ctx: dict) -> dict:
    """Check every cited claim against the source it cites."""
    provider_pool = ctx["provider_pool"]
    db_pool = ctx["db_pool"]
    user_id = ctx["user_id"]

    async with user_connection(db_pool, user_id) as conn:
        draft = await _stage_output(conn, job_id, "draft")
        sources = await conn.fetch(
            "SELECT id, title, content_text FROM sources WHERE job_id = $1",
            uuid.UUID(job_id),
        )

    if not draft or not draft.get("sections"):
        raise ValueError("Missing drafted sections to verify")

    source_map = {str(row["id"]).lower(): row for row in sources}
    results: list[dict] = []
    orphaned = 0

    for section in draft["sections"]:
        if section.get("status") == "failed":
            continue

        for claim_text, source_id in _extract_claims(section.get("content") or ""):
            source = source_map.get(source_id)
            if source is None:
                orphaned += 1
                continue

            prompt = (
                "You are a strict fact checker. Decide whether the source "
                "supports the claim.\n\n"
                f'CLAIM: "{claim_text[:1500]}"\n\n'
                f'SOURCE ({source["title"]}):\n'
                f'{(source["content_text"] or "")[:3000]}\n\n'
                "Answer with exactly one word: pass, unsupported, or "
                "contradicted."
            )

            try:
                verdict = (
                    (await provider_pool.call(prompt, tier="cheap"))
                    .strip()
                    .lower()
                    .strip(".\"' ")
                )
            except Exception as exc:
                logger.warning("[stage:verify] check failed: %s", exc)
                continue

            if verdict not in ("pass", "unsupported", "contradicted"):
                verdict = "unsupported"

            results.append(
                {
                    "source_id": source_id,
                    "claim_text": claim_text[:2000],
                    "verdict": verdict,
                }
            )

    if results:
        async with user_connection(db_pool, user_id) as conn:
            await conn.executemany(
                """
                INSERT INTO verification_results (job_id, source_id,
                                                  claim_text, verdict)
                VALUES ($1, $2, $3, $4::verdict_type)
                """,
                [
                    (
                        uuid.UUID(job_id),
                        uuid.UUID(item["source_id"]),
                        item["claim_text"],
                        item["verdict"],
                    )
                    for item in results
                ],
            )

    counts: dict[str, int] = {}
    for item in results:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1

    return {
        "verified_claims_count": len(results),
        "verdict_counts": counts,
        "orphaned_citations": orphaned,
        "results": results,
        "note": f"Checked {len(results)} claims",
    }


# ── Stage 5: Style ────────────────────────────────────────────

STYLE_PROMPT = """You are a precise academic editor.

Rewrite the section below for clarity and academic tone.

Rules:
1. Cut filler ("it is important to note", "basically", "in order to").
2. Replace vague attributions ("studies show", "experts say") with a
   concrete reference, or delete the sentence.
3. Tighten passive voice where an active form is clearer.
4. Keep every [cite: ...] tag exactly as written — do not add, remove,
   reorder, or reformat them.
5. Add no new claims or information.

SECTION: {header}

TEXT:
{content}

Return only the rewritten text."""


async def run_style(job_id: str, ctx: dict) -> dict:
    """Clarity pass that must not disturb the citation tags."""
    provider_pool = ctx["provider_pool"]
    db_pool = ctx["db_pool"]
    user_id = ctx["user_id"]

    async with user_connection(db_pool, user_id) as conn:
        draft = await _stage_output(conn, job_id, "draft")

    if not draft or not draft.get("sections"):
        raise ValueError("Missing drafted sections to style")

    styled_sections: list[dict] = []
    edits = 0
    rejected = 0

    for section in draft["sections"]:
        content = (section.get("content") or "").strip()
        if section.get("status") == "failed" or not content:
            styled_sections.append(section)
            continue

        header = section.get("header", "")
        content = section["content"]
        before_tags = CITE_PATTERN.findall(content)

        try:
            candidate = (
                await provider_pool.call(
                    STYLE_PROMPT.format(header=header, content=content),
                    tier="cheap",
                )
            ).strip()
        except Exception as exc:
            logger.warning("[stage:style] rewrite failed for %r: %s", header, exc)
            styled_sections.append(section)
            continue

        after_tags = CITE_PATTERN.findall(candidate)
        # A rewrite that drops or invents citations is worse than no rewrite.
        if not candidate or sorted(after_tags) != sorted(before_tags):
            rejected += 1
            logger.warning(
                "[stage:style] rejected rewrite for %r (citations changed)",
                header,
            )
            styled_sections.append(section)
            continue

        edits += 1
        styled_sections.append(
            {
                "header": header,
                "content": candidate,
                "status": section.get("status", "ok"),
            }
        )

    return {
        "sections": styled_sections,
        "edits_made": edits,
        "rewrites_rejected": rejected,
        "note": f"Styled {edits} sections",
    }


# ── Stage 6: Format ───────────────────────────────────────────


def _compile_markdown(title: str, sections: list[dict], references: list[dict]) -> str:
    parts = [f"# {title}\n"]
    for section in sections:
        if section.get("status") == "failed":
            continue
        parts.append(f"## {section['header']}\n")
        parts.append(f"{section['content']}\n")
    if references:
        parts.append("## References\n")
        for index, ref in enumerate(references, 1):
            line = f"[{index}] {ref.get('title') or 'Untitled'}"
            if ref.get("url"):
                line += f". {ref['url']}"
            parts.append(line)
    return "\n".join(parts).strip() + "\n"


async def run_format(job_id: str, ctx: dict) -> dict:
    """Number citations, compile Markdown, and render the DOCX."""
    db_pool = ctx["db_pool"]
    user_id = ctx["user_id"]
    settings = get_settings()

    async with user_connection(db_pool, user_id) as conn:
        job = await _load_job(conn, job_id)
        styled = await _stage_output(conn, job_id, "style")
        outline = await _stage_output(conn, job_id, "outline")
        verification = await _stage_output(conn, job_id, "verify")
        sources = await conn.fetch(
            "SELECT id, title, url FROM sources WHERE job_id = $1", uuid.UUID(job_id)
        )

    if not styled or not styled.get("sections"):
        raise ValueError("Missing styled sections to format")

    title = (outline or {}).get("title") or job["topic"]
    references = [
        {"id": str(row["id"]), "title": row["title"], "url": row["url"]}
        for row in sources
    ]

    sections, ordered_refs, unresolved = number_citations(
        styled["sections"], references
    )

    verification_section = build_verification_section(
        (verification or {}).get("results", [])
    )
    if verification_section:
        sections = sections + [verification_section]

    markdown = _compile_markdown(title, sections, ordered_refs)

    payload = {
        "job_id": job_id,
        "title": title,
        "sections": [
            {"header": s["header"], "body": s.get("content", "")}
            for s in sections
            if s.get("status") != "failed"
        ],
        "citation_style": job.get("citation_style") or "apa",
        "references": ordered_refs,
    }

    render_status = "skipped"
    document_id = None

    try:
        async with httpx.AsyncClient(timeout=settings.render_timeout_seconds) as client:
            response = await client.post(
                f"{settings.render_service_url}/render/docx", json=payload
            )
            response.raise_for_status()
            docx_bytes = response.content
    except Exception as exc:
        logger.warning(
            "[stage:format] render service unavailable (%s) — "
            "delivering Markdown only",
            exc,
        )
        render_status = "fallback_markdown"
        docx_bytes = None

    if docx_bytes:
        filename = f"humanoid_{job_id[:8]}.docx"
        async with user_connection(db_pool, user_id) as conn:
            document_id = await conn.fetchval(
                """
                INSERT INTO documents (job_id, kind, filename, mime_type,
                                       content, byte_size)
                VALUES ($1, 'docx', $2, $3, $4, $5)
                ON CONFLICT (job_id, kind) DO UPDATE
                   SET content = EXCLUDED.content,
                       byte_size = EXCLUDED.byte_size,
                       filename = EXCLUDED.filename
                RETURNING id
                """,
                uuid.UUID(job_id),
                filename,
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
                docx_bytes,
                len(docx_bytes),
            )
        render_status = "ok"

    return {
        "markdown": markdown,
        "title": title,
        "document_id": str(document_id) if document_id else None,
        "render_status": render_status,
        "citations": len(ordered_refs),
        "unresolved_citations": unresolved,
        "flagged_claims": len((verification or {}).get("results", [])),
        "note": (
            f"Compiled {len(sections)} sections, {len(ordered_refs)} citations"
            + (" + DOCX" if document_id else " (DOCX render unavailable)")
        ),
    }
