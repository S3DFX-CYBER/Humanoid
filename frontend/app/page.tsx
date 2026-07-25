"use client";

import { useState, useEffect, useRef } from "react";

/* ═══════════════════════════════════════════════════════════════
   Humanoid — Main Chat Interface
   Status text maps 1:1 to job_stage values from DB.
   ═══════════════════════════════════════════════════════════════ */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Maps directly to DB job_status enum
const STATUS_LABELS: Record<string, string> = {
    queued: "QUEUED",
    researching: "RESEARCHING SOURCES...",
    outlining: "GENERATING OUTLINE...",
    drafting: "DRAFTING SECTIONS...",
    verifying: "VERIFYING CLAIMS...",
    styling: "STYLE & CLARITY PASS...",
    formatting: "FORMATTING DOCUMENT...",
    done: "COMPLETE",
    failed: "FAILED",
};

interface Job {
    id: string;
    topic: string;
    status: string;
    created_at: string;
    updated_at: string;
}

interface LogEntry {
    timestamp: string;
    text: string;
    type: "status" | "info" | "error";
}

export default function Home() {
    const [topic, setTopic] = useState("");
    const [currentJob, setCurrentJob] = useState<Job | null>(null);
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [isPolling, setIsPolling] = useState(false);
    const logEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll log to bottom
    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    // Poll job status
    useEffect(() => {
        if (!currentJob || !isPolling) return;
        if (currentJob.status === "done" || currentJob.status === "failed") {
            setIsPolling(false);
            return;
        }

        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE}/jobs/${currentJob.id}`);
                if (!res.ok) return;
                const job: Job = await res.json();

                if (job.status !== currentJob.status) {
                    const label = STATUS_LABELS[job.status] || job.status.toUpperCase();
                    setLogs((prev: LogEntry[]) => [
                        ...prev,
                        {
                            timestamp: new Date().toISOString().split("T")[1].split(".")[0],
                            text: `[${label}]`,
                            type: job.status === "failed" ? "error" : "status",
                        },
                    ]);
                    setCurrentJob(job);

                    if (job.status === "done" || job.status === "failed") {
                        setIsPolling(false);
                    }
                }
            } catch {
                // Silently retry on next interval
            }
        }, 1500);

        return () => clearInterval(interval);
    }, [currentJob, isPolling]);

    const handleSubmit = async () => {
        if (!topic.trim()) return;

        setLogs([
            {
                timestamp: new Date().toISOString().split("T")[1].split(".")[0],
                text: `> ${topic}`,
                type: "info",
            },
            {
                timestamp: new Date().toISOString().split("T")[1].split(".")[0],
                text: "[QUEUED]",
                type: "status",
            },
        ]);

        try {
            const res = await fetch(`${API_BASE}/jobs`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    topic,
                    user_id: "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", // dev user
                }),
            });

            if (!res.ok) {
                setLogs((prev: LogEntry[]) => [
                    ...prev,
                    {
                        timestamp: new Date().toISOString().split("T")[1].split(".")[0],
                        text: "[ERROR] Failed to create job",
                        type: "error",
                    },
                ]);
                return;
            }

            const job: Job = await res.json();
            setCurrentJob(job);
            setIsPolling(true);
            setTopic("");
        } catch {
            setLogs((prev: LogEntry[]) => [
                ...prev,
                {
                    timestamp: new Date().toISOString().split("T")[1].split(".")[0],
                    text: "[ERROR] Cannot reach API",
                    type: "error",
                },
            ]);
        }
    };

    return (
        <div style={{ display: "flex", minHeight: "100vh" }}>
            {/* ── Sidebar ──────────────────────────────────── */}
            <aside className="sidebar">
                <div style={{ padding: "var(--space-sm) 0" }}>
                    <h1
                        className="type-headline-md"
                        style={{ fontWeight: 700, letterSpacing: "-0.02em" }}
                    >
                        HUMANOID
                    </h1>
                    <p
                        className="type-mono-label"
                        style={{
                            color: "var(--color-secondary)",
                            marginTop: "var(--space-base)",
                        }}
                    >
                        RESEARCH ASSISTANT
                    </p>
                </div>

                <div className="divider" style={{ margin: "var(--space-sm) 0" }} />

                <nav>
                    <div className="sidebar-nav-item sidebar-nav-item-active">
                        Chat
                    </div>
                    <div className="sidebar-nav-item">Sources</div>
                    <div className="sidebar-nav-item">Documents</div>
                </nav>
            </aside>

            {/* ── Main Content ─────────────────────────────── */}
            <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                {/* Header */}
                <header
                    style={{
                        padding: "var(--space-sm) var(--space-md)",
                        borderBottom: "1px solid var(--color-border)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}
                >
                    <span className="type-body-sm" style={{ color: "var(--color-secondary)" }}>
                        {currentJob
                            ? `Job: ${currentJob.id.slice(0, 8)}...`
                            : "New Research"}
                    </span>
                    {currentJob && (
                        <span className="type-mono-label">
                            {STATUS_LABELS[currentJob.status] || currentJob.status}
                        </span>
                    )}
                </header>

                {/* Chat / Log Area */}
                <div
                    style={{
                        flex: 1,
                        overflow: "auto",
                        padding: "var(--space-md)",
                    }}
                >
                    {logs.length === 0 ? (
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                height: "100%",
                                flexDirection: "column",
                                gap: "var(--space-sm)",
                            }}
                        >
                            <h2 className="type-headline-lg">What would you like to research?</h2>
                            <p
                                className="type-body-sm"
                                style={{ color: "var(--color-secondary)", maxWidth: 480, textAlign: "center" }}
                            >
                                Enter a topic or research question. Humanoid will find sources,
                                draft a structured document, verify claims, and format the result
                                for submission.
                            </p>
                        </div>
                    ) : (
                        <div style={{ maxWidth: 720 }}>
                            {logs.map((log, i) => (
                                <div
                                    key={i}
                                    className={
                                        log.type === "info"
                                            ? "chat-message chat-message-user"
                                            : "chat-message chat-message-ai"
                                    }
                                >
                                    <span
                                        className="type-mono-code"
                                        style={{
                                            color:
                                                log.type === "error"
                                                    ? "var(--color-on-surface)"
                                                    : log.type === "status"
                                                        ? "var(--color-on-surface-variant)"
                                                        : "var(--color-on-surface)",
                                            fontWeight: log.type === "error" ? 700 : 400,
                                        }}
                                    >
                                        <span style={{ color: "var(--color-secondary)", marginRight: 8 }}>
                                            {log.timestamp}
                                        </span>
                                        {log.text}
                                    </span>
                                </div>
                            ))}
                            <div ref={logEndRef} />
                        </div>
                    )}
                </div>

                {/* Input Area */}
                <div
                    style={{
                        padding: "var(--space-sm) var(--space-md)",
                        borderTop: "1px solid var(--color-border)",
                    }}
                >
                    <div style={{ display: "flex", gap: "var(--space-xs)", maxWidth: 720 }}>
                        <input
                            className="input-field"
                            type="text"
                            placeholder="Enter a research topic or question..."
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") handleSubmit();
                            }}
                            disabled={isPolling}
                            id="research-topic-input"
                        />
                        <button
                            className="btn btn-primary"
                            onClick={handleSubmit}
                            disabled={isPolling || !topic.trim()}
                            id="submit-research-btn"
                            style={{ whiteSpace: "nowrap" }}
                        >
                            {isPolling ? "RUNNING..." : "RESEARCH"}
                        </button>
                    </div>
                </div>
            </main>
        </div>
    );
}
