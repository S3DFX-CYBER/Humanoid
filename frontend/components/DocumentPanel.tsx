"use client";

import { useEffect, useState } from "react";

import { api, ApiError, type DocumentInfo } from "../lib/api";

interface Props {
  jobId: string;
  isDone: boolean;
}

export function DocumentPanel({ jobId, isDone }: Props) {
  const [documentInfo, setDocumentInfo] = useState<DocumentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!isDone) {
      setDocumentInfo(null);
      return;
    }

    const controller = new AbortController();
    api
      .getDocument(jobId, controller.signal)
      .then(setDocumentInfo)
      .catch((caught) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(
          caught instanceof ApiError ? caught.message : "Could not load the result.",
        );
      });

    return () => controller.abort();
  }, [jobId, isDone]);

  if (!isDone) return null;

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await api.downloadDocument(jobId);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Download failed.",
      );
    } finally {
      setDownloading(false);
    }
  }

  const hasDocx = documentInfo?.has_docx ?? false;

  return (
    <section className="document-panel" aria-label="Finished document">
      <div className="document-header">
        <div>
          <p className="type-mono-label">DOCUMENT</p>
          <p className="type-body-sm muted" style={{ marginTop: 4 }}>
            {hasDocx
              ? `Ready to download${documentInfo?.byte_size ? ` · ${Math.round(documentInfo.byte_size / 1024)} KB` : ""}`
              : "Word export is unavailable — the Markdown version is below."}
          </p>
        </div>
        <button
          className="btn btn-primary"
          type="button"
          onClick={handleDownload}
          disabled={downloading}
        >
          {downloading ? "Preparing…" : hasDocx ? "Download .docx" : "Download .md"}
        </button>
      </div>

      {error && (
        <p className="banner banner-error" role="alert">
          {error}
        </p>
      )}

      {documentInfo?.markdown && (
        <details className="document-preview">
          <summary className="type-label-caps">Preview the document</summary>
          <pre className="type-mono-code document-body">
            {documentInfo.markdown}
          </pre>
        </details>
      )}
    </section>
  );
}
