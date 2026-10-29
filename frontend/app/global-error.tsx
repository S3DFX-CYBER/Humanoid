"use client";

/* Root error boundary.
 *
 * `app/error.tsx` cannot catch a failure in the root layout itself. This one
 * can, and it must render its own <html> and <body> because it replaces the
 * layout entirely. It deliberately avoids the design-system classes that come
 * from globals.css: if the failure happened while loading styles, those classes
 * would not exist.
 */

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[humanoid] fatal error", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#f9f9f9",
          color: "#1a1c1c",
          fontFamily:
            "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          padding: 24,
        }}
      >
        <div style={{ maxWidth: 420 }}>
          <p style={{ fontSize: 11, letterSpacing: "0.04em", margin: 0 }}>
            HUMANOID
          </p>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: "8px 0 0" }}>
            The app could not start
          </h1>
          <p style={{ fontSize: 14, lineHeight: 1.6, margin: "8px 0 0" }}>
            This is usually a configuration problem rather than lost data. Check
            the deployment&apos;s function logs for the reference below.
          </p>
          {error.digest && (
            <p style={{ fontFamily: "monospace", fontSize: 12, margin: "16px 0 0" }}>
              REFERENCE {error.digest}
            </p>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 24 }}>
            <button
              type="button"
              onClick={reset}
              style={{
                minHeight: 44,
                padding: "10px 20px",
                fontSize: 14,
                border: "none",
                borderRadius: 4,
                background: "#000",
                color: "#fff",
                cursor: "pointer",
              }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
