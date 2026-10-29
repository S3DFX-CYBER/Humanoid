"""Citation numbering: turn internal source UUIDs into readable [1], [2] markers.

Drafting emits ``[cite: <source-uuid>]`` so claims stay machine-verifiable.
Humans must never see a UUID, so the format stage rewrites those tags into
sequential numbers and builds a bibliography ordered by first appearance.
"""

import re

CITE_RE = re.compile(r"\[cite:\s*([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})\s*\]")
LEFTOVER_CITE_RE = re.compile(r"\[cite:[^\]]*\]")


def number_citations(
    sections: list[dict],
    references: list[dict],
) -> tuple[list[dict], list[dict], int]:
    """Rewrite cite tags into numbers.

    Returns ``(sections, ordered_references, unresolved_count)`` where
    ``ordered_references`` contains only the sources actually cited, in
    order of first appearance.
    """
    order: dict[str, int] = {}

    def _replace(match: re.Match) -> str:
        source_id = match.group(1).lower()
        if source_id not in order:
            order[source_id] = len(order) + 1
        return f"[{order[source_id]}]"

    renumbered: list[dict] = []
    for section in sections:
        content = section.get("content") or ""
        content = CITE_RE.sub(_replace, content)
        # Anything left is a malformed or orphaned tag — never ship raw UUIDs.
        content = LEFTOVER_CITE_RE.sub("", content)
        renumbered.append({**section, "content": content})

    by_id = {str(ref["id"]).lower(): ref for ref in references}
    ordered = [by_id[source_id] for source_id in order if source_id in by_id]
    unresolved = sum(1 for source_id in order if source_id not in by_id)

    return renumbered, ordered, unresolved


def build_verification_section(results: list[dict]) -> dict | None:
    """Summarise claims the fact-checker could not support.

    The README promises that unsupported claims are flagged rather than
    quietly shipped, so they surface in the document itself.
    """
    flagged = [
        r
        for r in results
        if str(r.get("verdict", "")).lower() in ("unsupported", "contradicted")
    ]
    if not flagged:
        return None

    lines = [
        "The following claims could not be fully supported by the cited "
        "sources and should be reviewed before submission:",
        "",
    ]
    for item in flagged:
        verdict = str(item.get("verdict", "")).upper()
        claim = (item.get("claim_text") or "").strip()
        if len(claim) > 300:
            claim = claim[:300].rsplit(" ", 1)[0] + "…"
        lines.append(f"- [{verdict}] {claim}")

    return {
        "header": "Verification notes",
        "content": "\n\n".join([" ".join(lines[:2]), "\n".join(lines[2:])]),
        "status": "ok",
    }
