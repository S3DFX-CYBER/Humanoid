"use client";

/* Route-level error boundary.
 *
 * Without this, any render error in the app is replaced by the platform's
 * generic "This page is unavailable / FUNCTION_INVOCATION_FAILED" page, which
 * tells the person looking at it nothing and gives them nothing to do. This
 * renders the actual message and a way forward, in the product's own voice.
 */

import { useEffect } from "react";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surfaces in the browser console and in the platform's function logs.
    console.error("[humanoid] render error", error);
  }, [error]);

  return (
    <main className="auth-shell">
      <div className="auth-card">
        <p className="type-mono-label">HUMANOID</p>
        <h1 className="type-headline-lg" style={{ marginTop: "var(--space-xs)" }}>
          Something broke on this screen
        </h1>
        <p className="type-body-sm muted" style={{ marginTop: "var(--space-xs)" }}>
          The interface failed to render. Your jobs and documents are unaffected
          — they live on the server, not in this page.
        </p>

        {error.digest && (
          <p className="type-mono-label muted" style={{ marginTop: "var(--space-sm)" }}>
            REFERENCE {error.digest}
          </p>
        )}

        <div style={{ display: "flex", gap: "var(--space-xs)", marginTop: "var(--space-md)" }}>
          <button className="btn btn-primary" type="button" onClick={reset}>
            Try again
          </button>
          <a className="btn btn-secondary" href="/">
            Reload the workspace
          </a>
        </div>
      </div>
    </main>
  );
}
