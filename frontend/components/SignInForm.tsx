"use client";

import { useState } from "react";

import { api, ApiError } from "../lib/api";

export function SignInForm({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      await api.signIn(email.trim(), password);
      onSignedIn();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Could not sign in.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <div className="auth-card">
        <p className="type-mono-label">HUMANOID</p>
        <h1 className="type-headline-lg" style={{ marginTop: "var(--space-xs)" }}>
          Sign in to continue
        </h1>
        <p className="type-body-sm muted" style={{ marginTop: "var(--space-xs)" }}>
          Your research, sources, and documents are private to your account.
        </p>

        <form onSubmit={handleSubmit} style={{ marginTop: "var(--space-md)" }}>
          <label className="input-label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            className="input-field"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <label
            className="input-label"
            htmlFor="password"
            style={{ marginTop: "var(--space-sm)" }}
          >
            Password
          </label>
          <input
            id="password"
            className="input-field"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {error && (
            <p className="banner banner-error" role="alert">
              {error}
            </p>
          )}

          <button
            className="btn btn-primary"
            type="submit"
            disabled={busy || !email || !password}
            style={{ marginTop: "var(--space-md)", width: "100%" }}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
