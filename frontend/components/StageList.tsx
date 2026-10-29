"use client";

import type { Stage } from "../lib/api";

const STAGE_LABELS: Record<string, string> = {
  research: "Research sources",
  outline: "Build outline",
  draft: "Draft sections",
  verify: "Verify claims",
  style: "Style & clarity",
  format: "Format document",
};

const STATUS_TEXT: Record<Stage["status"], string> = {
  pending: "WAITING",
  running: "RUNNING",
  completed: "DONE",
  failed: "FAILED",
};

function summarise(stage: Stage): string | null {
  const output = stage.output_data ?? {};

  switch (stage.stage_name) {
    case "research": {
      const count = output.sources_found;
      return typeof count === "number" ? `${count} sources` : null;
    }
    case "outline": {
      const sections = output.sections;
      return Array.isArray(sections) ? `${sections.length} sections` : null;
    }
    case "verify": {
      const count = output.verified_claims_count;
      return typeof count === "number" ? `${count} claims checked` : null;
    }
    case "style": {
      const edits = output.edits_made;
      return typeof edits === "number" ? `${edits} sections tightened` : null;
    }
    case "format": {
      const citations = output.citations;
      const status = output.render_status;
      if (status === "fallback_markdown") return "Markdown only";
      return typeof citations === "number" ? `${citations} citations` : null;
    }
    default:
      return null;
  }
}

export function StageList({ stages }: { stages: Stage[] }) {
  if (stages.length === 0) return null;

  return (
    <section aria-label="Pipeline progress" className="stage-list">
      {stages.map((stage) => {
        const summary = summarise(stage);
        return (
          <div className="stage-row" key={stage.id}>
            <span
              className={
                stage.status === "running"
                  ? "stage-status stage-status-active"
                  : "stage-status"
              }
            >
              [{STATUS_TEXT[stage.status]}]
            </span>
            <span className="stage-name">
              {STAGE_LABELS[stage.stage_name] ?? stage.stage_name}
            </span>
            {summary && <span className="stage-meta">{summary}</span>}
            {stage.status === "failed" && stage.error && (
              <span className="stage-error">{stage.error}</span>
            )}
          </div>
        );
      })}
    </section>
  );
}
