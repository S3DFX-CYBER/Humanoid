/* Typed API client for the Humanoid backend.
 *
 * Every request carries the Supabase access token from localStorage. In local
 * development the API can run with DEV_AUTH_USER_ID set, in which case the
 * token is optional and NEXT_PUBLIC_DEV_MODE skips the sign-in screen.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const DEV_MODE = process.env.NEXT_PUBLIC_DEV_MODE === "true";

const TOKEN_KEY = "humanoid.access_token";
const EMAIL_KEY = "humanoid.email";

export type JobStatus =
  | "queued"
  | "researching"
  | "outlining"
  | "outline_pending_approval"
  | "drafting"
  | "verifying"
  | "styling"
  | "formatting"
  | "done"
  | "failed";

export interface Job {
  id: string;
  user_id: string;
  topic: string;
  status: JobStatus;
  citation_style: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Stage {
  id: string;
  job_id: string;
  stage_name: string;
  status: "pending" | "running" | "completed" | "failed";
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface DocumentInfo {
  job_id: string;
  has_docx: boolean;
  markdown: string | null;
  filename: string | null;
  byte_size: number | null;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(EMAIL_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Humanoid API. Is it running?");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
        detail = String(body.detail[0].msg);
      }
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    if (response.status === 401) {
      detail = "Your session has expired. Please sign in again.";
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  async signIn(email: string, password: string): Promise<void> {
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
      throw new ApiError(
        0,
        "Supabase is not configured for this build. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, or enable NEXT_PUBLIC_DEV_MODE for local work.",
      );
    }

    const response = await fetch(
      `${SUPABASE_URL}/auth/v1/token?grant_type=password`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: SUPABASE_ANON_KEY,
        },
        body: JSON.stringify({ email, password }),
      },
    );

    if (!response.ok) {
      throw new ApiError(
        response.status,
        response.status === 400
          ? "That email and password combination was not recognised."
          : "Could not sign in. Please try again.",
      );
    }

    const body = (await response.json()) as { access_token?: string };
    if (!body.access_token) {
      throw new ApiError(0, "Sign-in succeeded but no session token was returned.");
    }

    window.localStorage.setItem(TOKEN_KEY, body.access_token);
    window.localStorage.setItem(EMAIL_KEY, email);
  },

  signOut(): void {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(EMAIL_KEY);
  },

  createJob(topic: string, citationStyle = "apa"): Promise<Job> {
    return request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify({ topic, citation_style: citationStyle }),
    });
  },

  getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
    return request<Job>(`/jobs/${jobId}`, { signal });
  },

  listStages(jobId: string, signal?: AbortSignal): Promise<Stage[]> {
    return request<Stage[]>(`/jobs/${jobId}/stages`, { signal });
  },

  getDocument(jobId: string, signal?: AbortSignal): Promise<DocumentInfo> {
    return request<DocumentInfo>(`/jobs/${jobId}/document`, { signal });
  },

  retryJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}/retry`, { method: "POST" });
  },

  async downloadDocument(jobId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/jobs/${jobId}/document/file`, {
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new ApiError(response.status, "The document is not ready yet.");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `humanoid-${jobId.slice(0, 8)}.docx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
