"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { DocumentPanel } from "../components/DocumentPanel";
import { SignInForm } from "../components/SignInForm";
import { StageList } from "../components/StageList";
import { api, DEV_MODE, getEmail, getToken, type JobStatus } from "../lib/api";
import { useResearchJob } from "../lib/useResearchJob";

const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  researching: "Researching sources",
  outlining: "Building the outline",
  outline_pending_approval: "Waiting for your approval",
  drafting: "Drafting sections",
  verifying: "Verifying claims",
  styling: "Style and clarity pass",
  formatting: "Formatting the document",
  done: "Complete",
  failed: "Stopped",
};

const EXAMPLES = [
  "How transformer architectures changed machine translation",
  "Evidence for and against four-day work weeks",
  "Cooling efficiency of district energy systems in Indian cities",
];

export default function Home() {
  const [signedIn, setSignedIn] = useState(DEV_MODE);
  const [topic, setTopic] = useState("");
  const [citationStyle, setCitationStyle] = useState("apa");
  const inputRef = useRef<HTMLInputElement>(null);

  const { job, stages, error, isRunning, start, retry, reset } = useResearchJob();

  useEffect(() => {
    if (DEV_MODE) return;
    setSignedIn(Boolean(getToken()));
  }, []);

  const isDone = job?.status === "done";
  const hasJob = job !== null;
  const email = useMemo(() => (signedIn ? getEmail() : null), [signedIn]);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = topic.trim();
    if (trimmed.length < 3 || isRunning) return;
    setTopic("");
    void start(trimmed, citationStyle);
  }

  function handleSignOut() {
    api.signOut();
    setSignedIn(false);
    reset();
  }

  if (!signedIn) {
    return <SignInForm onSignedIn={() => setSignedIn(true)} />;
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>

      <aside className="sidebar">
        <div>
          <h1 className="type-headline-md" style={{ fontWeight: 700 }}>
            HUMANOID
          </h1>
          <p className="type-mono-label muted" style={{ marginTop: 4 }}>
            RESEARCH ASSISTANT
          </p>
        </div>

        <div className="divider" style={{ margin: "var(--space-sm) 0" }} />

        <nav aria-label="Sections">
          <a className="sidebar-nav-item sidebar-nav-item-active" href="#workspace">
            Research
          </a>
          <span className="sidebar-nav-item sidebar-nav-item-disabled">
            Sources
            <span className="type-mono-label">SOON</span>
          </span>
          <span className="sidebar-nav-item sidebar-nav-item-disabled">
            Library
            <span className="type-mono-label">SOON</span>
          </span>
        </nav>

        <div className="sidebar-footer">
          {email && <p className="type-mono-label muted">{email}</p>}
          {!DEV_MODE && (
            <button className="btn btn-ghost" type="button" onClick={handleSignOut}>
              Sign out
            </button>
          )}
          {DEV_MODE && (
            <p className="type-mono-label muted">DEV MODE · AUTH BYPASSED</p>
          )}
        </div>
      </aside>

      <main id="workspace" className="workspace">
        <header className="workspace-header">
          <div>
            <p className="type-mono-label muted">
              {hasJob ? `JOB ${job.id.slice(0, 8)}` : "NEW RESEARCH"}
            </p>
            <p className="type-body-sm" style={{ marginTop: 4 }}>
              {hasJob ? job.topic : "Describe what you want researched."}
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
            {hasJob && (
              <span className="type-mono-label" aria-live="polite">
                {STATUS_LABELS[job.status]}
              </span>
            )}
            {hasJob && !isRunning && (
              <button className="btn btn-secondary" type="button" onClick={reset}>
                New research
              </button>
            )}
          </div>
        </header>

        <div className="workspace-body">
          {!hasJob && (
            <section className="empty-state">
              <h2 className="type-headline-lg">What should we research?</h2>
              <p className="type-body-sm muted empty-state-copy">
                Humanoid finds sources, drafts a structured document, checks
                every claim against its citation, and hands you a finished file.
              </p>

              <ul className="example-list">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      className="example-chip"
                      type="button"
                      onClick={() => {
                        setTopic(example);
                        inputRef.current?.focus();
                      }}
                    >
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {hasJob && (
            <div className="result-column">
              <StageList stages={stages} />

              {job.status === "failed" && (
                <div className="banner banner-error" role="alert">
                  <p>{error ?? "This job stopped before finishing."}</p>
                  <button className="btn btn-secondary" type="button" onClick={() => void retry()}>
                    Continue from the last completed step
                  </button>
                </div>
              )}

              {error && job.status !== "failed" && (
                <p className="banner banner-error" role="alert">
                  {error}
                </p>
              )}

              <DocumentPanel jobId={job.id} isDone={isDone} />
            </div>
          )}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <label className="input-label" htmlFor="research-topic">
            Research topic
          </label>

          <div className="composer-row">
            <input
              id="research-topic"
              ref={inputRef}
              className="input-field"
              type="text"
              placeholder="e.g. How do retrieval-augmented models reduce hallucination?"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              disabled={isRunning}
              maxLength={500}
              autoComplete="off"
            />

            <label className="sr-only" htmlFor="citation-style">
              Citation style
            </label>
            <select
              id="citation-style"
              className="input-field select-field"
              value={citationStyle}
              onChange={(event) => setCitationStyle(event.target.value)}
              disabled={isRunning}
            >
              <option value="apa">APA</option>
              <option value="mla">MLA</option>
              <option value="chicago">Chicago</option>
              <option value="ieee">IEEE</option>
            </select>

            <button
              className="btn btn-primary"
              type="submit"
              disabled={isRunning || topic.trim().length < 3}
              aria-busy={isRunning}
            >
              {isRunning ? "Researching…" : "Start research"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
