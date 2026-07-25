"""Pipeline stage handler stubs.

Each stage is an async function that receives the job context and
produces output. In Phase 0 these are no-ops — real logic comes in
later phases.

Stage order:
  researching → outlining → drafting → verifying → styling → formatting
"""

import logging

logger = logging.getLogger(__name__)


import json
import uuid
from providers.search import get_search_results, fetch_and_extract_text
from providers.embedding import generate_embedding

async def run_research(job_id: str, input_data: dict) -> dict:
    """Stage 1: Research sources for the given topic."""
    logger.info("[stage:research] job=%s — beginning real search", job_id)
    
    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]
    
    # 1. Fetch job topic & user_id
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id))
        if not job:
            raise ValueError(f"Job {job_id} not found")
        topic = job["topic"]
        user_id = job["user_id"]

    # 2. Generate Search Queries using LLM
    search_prompt = (
        f"You are an expert researcher. The user's topic is: '{topic}'.\n"
        "Generate 2 highly specific, distinct web search queries to find the most credible, authoritative information about this topic.\n"
        "Output ONLY a JSON array of strings. Example: [\"query 1\", \"query 2\"]"
    )
    
    try:
        queries_json = await provider_pool.call(search_prompt, tier="cheap")
        # Strip markdown formatting just in case
        queries_json = queries_json.replace("```json", "").replace("```", "").strip()
        queries = json.loads(queries_json)
        if not isinstance(queries, list):
            queries = [topic]
    except Exception as e:
        logger.error(f"[stage:research] Failed to generate queries: {e}")
        queries = [topic]

    queries = queries[:2]  # hard limit to 2 queries for speed
    
    # 3. Execute Searches & Fetch Content
    sources_saved = 0
    for q in queries:
        results = await get_search_results(q, max_results=2)
        for res in results:
            url = res.get("href")
            title = res.get("title", "Untitled")
            
            # Fetch actual page content
            content = await fetch_and_extract_text(url, max_chars=4000)
            if not content:
                content = res.get("body", "") # Fallback to snippet if fetch fails
                
            if len(content) < 50:
                continue
                
            # 4. Generate Embedding for the content
            vector = await generate_embedding(content)
            
            # 5. Store in Postgres via db_pool (inject RLS context explicitly)
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(f"SET LOCAL jwt.claims.sub = '{user_id}'")
                    await conn.execute(
                        """
                        INSERT INTO sources (job_id, url, title, content_text, source_type, embedding)
                        VALUES ($1, $2, $3, $4, 'web', $5::vector)
                        """,
                        uuid.UUID(job_id),
                        url,
                        title,
                        content,
                        vector
                    )
            sources_saved += 1
            
    return {
        "queries_used": queries,
        "sources_found": sources_saved, 
        "note": f"Completed research for topic: {topic}"
    }


async def run_outline(job_id: str, input_data: dict) -> dict:
    """Stage 2: Generate thesis + outline using sources from Stage 1."""
    logger.info("[stage:outline] job=%s — generating outline", job_id)
    
    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]
    
    # Fetch job context and sources
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id))
        
        # We also need the content from the sources found in standard user contexts
        # We will use the user context for RLS
        async with conn.transaction():
            await conn.execute(f"SET LOCAL jwt.claims.sub = '{job['user_id']}'")
            sources = await conn.fetch(
                "SELECT title, content_text FROM sources WHERE job_id = $1 LIMIT 5",
                uuid.UUID(job_id)
            )

    topic = job["topic"]
    
    source_context = ""
    for i, s in enumerate(sources):
        # Truncate content to avoid crazy huge prompts if pages were large
        text = s["content_text"][:2000]
        source_context += f"Source {i+1}: {s['title']}\n{text}\n\n"
        
    prompt = f"""You are an expert researcher writing an academic outline on the topic: '{topic}'.
Review the following excerpts from our research phase:

{source_context}

Based off these sources, write a comprehensive outline for an authoritative article.
Return your response STRICTLY as a JSON object with the following schema, and no markdown formatting or backticks:
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
        # Clean json
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        outline_json = json.loads(response_text)
    except Exception as e:
        logger.error(f"[stage:outline] Failed to parse generated outline: {e}")
        # generic fallback outline
        outline_json = {
            "title": f"Report on {topic}",
            "thesis": topic,
            "sections": ["Introduction", "Main Body", "Conclusion"]
        }

    return outline_json


async def run_draft(job_id: str, input_data: dict) -> dict:
    """Stage 3: Draft section-by-section with source-tagged claims."""
    logger.info("[stage:draft] job=%s — drafting content", job_id)
    
    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]
    
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id))
        
        async with conn.transaction():
            await conn.execute(f"SET LOCAL jwt.claims.sub = '{job['user_id']}'")
            
            # 1. Fetch Outline from previous stage
            outline_row = await conn.fetchrow(
                "SELECT output_data FROM job_stages WHERE job_id = $1 AND stage_name = 'outlining' AND status = 'completed' ORDER BY completed_at DESC LIMIT 1",
                uuid.UUID(job_id)
            )
            outline_data = outline_row["output_data"] if outline_row else None
            if isinstance(outline_data, str):
                outline_data = json.loads(outline_data)
                
            # 2. Fetch all sources to supply as RAG context
            sources = await conn.fetch("SELECT id, title, content_text FROM sources WHERE job_id = $1", uuid.UUID(job_id))

    if not outline_data or "sections" not in outline_data:
        raise ValueError("Missing outline data to begin drafting")
        
    topic = job["topic"]
    thesis = outline_data.get("thesis", topic)
    
    # 3. Build Source Context (with IDs for tagging)
    source_context = ""
    for s in sources:
        text = s["content_text"][:1000] # clamp to 1000 chars per source for drafting
        source_context += f"Source ID: {s['id']}\nTitle: {s['title']}\n{text}\n\n"
        
    drafted_sections = []
    
    # 4. Draft section by section
    for section_outline in outline_data["sections"]:
        prompt = f"""You are an advanced academic writer. Write the following section for an article.
Topic: {topic}
Overall Thesis: {thesis}

Target Section Objective: {section_outline}

Available Research Context:
{source_context}

INSTRUCTIONS:
1. Write 2-3 comprehensive paragraphs for this section based MUST ONLY on the provided sources.
2. Whenever you make a factual claim, you MUST append a citation tag using the EXACT format: [cite: <SOURCE_ID>]. Do not invent facts, only use the Context.
3. Write ONLY the text for the section, do not include the section header yourself.
"""
        try:
            content = await provider_pool.call(prompt, tier="premium")
            drafted_sections.append({
                "header": section_outline,
                "content": content.strip()
            })
        except Exception as e:
            logger.error(f"[stage:draft] Failed drafting section '{section_outline}': {e}")
            drafted_sections.append({
                "header": section_outline,
                "content": "[Drafting failed for this section]"
            })
            
    return {"sections": drafted_sections, "note": f"Drafted {len(drafted_sections)} sections"}


import re

async def run_verify(job_id: str, input_data: dict) -> dict:
    """Stage 4: Verify each claim against its cited source."""
    logger.info("[stage:verify] job=%s — beginning verification", job_id)
    
    provider_pool = input_data["provider_pool"]
    db_pool = input_data["db_pool"]
    
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT topic, user_id FROM jobs WHERE id = $1", uuid.UUID(job_id))
        
        async with conn.transaction():
            await conn.execute(f"SET LOCAL jwt.claims.sub = '{job['user_id']}'")
            
            # Fetch drafted sections
            draft_row = await conn.fetchrow(
                "SELECT output_data FROM job_stages WHERE job_id = $1 AND stage_name = 'drafting' AND status = 'completed' ORDER BY completed_at DESC LIMIT 1",
                uuid.UUID(job_id)
            )
            draft_data = draft_row["output_data"] if draft_row else None
            if isinstance(draft_data, str):
                draft_data = json.loads(draft_data)
                
            sources_records = await conn.fetch("SELECT id, title, content_text FROM sources WHERE job_id = $1", uuid.UUID(job_id))
            
    if not draft_data or "sections" not in draft_data:
        raise ValueError("Missing drafted sections data to verify")
        
    source_map = {str(s["id"]): s for s in sources_records}
    
    verified_claims = 0
    verification_results = []
    
    # regex to find [cite: UUID]
    cite_pattern = re.compile(r"\[cite:\s*([a-f0-9\-]+)\]")
    
    for section in draft_data["sections"]:
        content = section.get("content", "")
        # Find all sentences with citations
        sentences = [s.strip() for s in content.split(".") if "[cite:" in s]
        
        for sentence in sentences:
            matches = cite_pattern.findall(sentence)
            for source_id in matches:
                # verify this claim against this source
                if source_id not in source_map:
                    continue  # orphaned citation
                    
                source_text = source_map[source_id]["content_text"][:2000]
                
                verify_prompt = f"""You are a fact checker. Verify the following claim against the provided source.
Claim: "{sentence}"
Source Text: "{source_text}"

Does the source support the claim?
Return ONLY 'pass', 'unsupported', or 'contradicted' (lowercase, single word)."""
                
                try:
                    verdict = (await provider_pool.call(verify_prompt, tier="cheap")).strip().lower()
                    if verdict not in ("pass", "unsupported", "contradicted"):
                        verdict = "unsupported"
                        
                    verification_results.append({
                        "job_id": job_id,
                        "source_id": source_id,
                        "claim_text": sentence,
                        "verdict": verdict
                    })
                    verified_claims += 1
                except Exception as e:
                    logger.warning(f"[stage:verify] Verification call failed: {e}")
                    
    # Bulk insert verification results
    if verification_results:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL jwt.claims.sub = '{job['user_id']}'")
                for r in verification_results:
                    await conn.execute(
                        """
                        INSERT INTO verification_results (job_id, source_id, claim_text, verdict)
                        VALUES ($1, $2, $3, $4)
                        """,
                        uuid.UUID(r["job_id"]),
                        uuid.UUID(r["source_id"]),
                        r["claim_text"],
                        r["verdict"]
                    )
                    
    return {
        "verified_claims_count": verified_claims,
        "results": verification_results,
        "note": f"Verified {verified_claims} claims"
    }


async def run_style(job_id: str, input_data: dict) -> dict:
    """Stage 5: Style & clarity pass."""
    logger.info("[stage:style] job=%s — styling pass", job_id)
    
    db_pool = input_data["db_pool"]
    
    async with db_pool.acquire() as conn:
        draft_row = await conn.fetchrow(
            "SELECT output_data FROM job_stages WHERE job_id = $1 AND stage_name = 'drafting' AND status = 'completed' ORDER BY completed_at DESC LIMIT 1",
            uuid.UUID(job_id)
        )
        
    draft_data = draft_row["output_data"] if draft_row else None
    if isinstance(draft_data, str):
        draft_data = json.loads(draft_data)
        
    if not draft_data or "sections" not in draft_data:
        raise ValueError("Missing drafted sections data to style")

    # In a full run, the LLM would rewrite sections for flow.
    # For now, we perform a deterministic cleanup.
    cleaned_sections = []
    for section in draft_data["sections"]:
        content = section.get("content", "")
        # Very simple cleanup (e.g., removing double spaces)
        content = content.replace("  ", " ").strip()
        cleaned_sections.append({
            "header": section.get("header", ""),
            "content": content
        })
        
    return {"sections": cleaned_sections, "edits_made": 0, "note": "Styling complete"}


async def run_format(job_id: str, input_data: dict) -> dict:
    """Stage 6: Format into submission-ready document."""
    logger.info("[stage:format] job=%s — formatting final document", job_id)
    
    db_pool = input_data["db_pool"]
    
    async with db_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT topic FROM jobs WHERE id = $1", uuid.UUID(job_id))
        
        style_row = await conn.fetchrow(
            "SELECT output_data FROM job_stages WHERE job_id = $1 AND stage_name = 'styling' AND status = 'completed' ORDER BY completed_at DESC LIMIT 1",
            uuid.UUID(job_id)
        )
        
    style_data = style_row["output_data"] if style_row else None
    if isinstance(style_data, str):
        style_data = json.loads(style_data)
        
    if not style_data or "sections" not in style_data:
        raise ValueError("Missing styled sections data to format")

    topic = job["topic"]
    
    # Simple Markdown compilation
    markdown_doc = f"# {topic.title()}\n\n"
    
    for section in style_data["sections"]:
        markdown_doc += f"## {section['header']}\n\n"
        markdown_doc += f"{section['content']}\n\n"
        
    logger.info(f"[stage:format] Markdown document compiled ({len(markdown_doc)} bytes)")
    
    # TODO: In the future, pass to Render microservice for DOCX/PDF generation.
    return {
        "markdown": markdown_doc,
        "document_url": None, 
        "note": "Compiled into markdown"
    }
