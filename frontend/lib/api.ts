/**
 * Thin fetch wrapper for the GRMT backend API — master build document §5.
 * Attaches the JWT bearer token from localStorage (see lib/auth-context.tsx)
 * and normalizes the {error: {code, message}} shape from §5.10 into a
 * throwable ApiError.
 *
 * NOTE: localStorage is used here for simplicity in this starter scaffold.
 * Before production, revisit token storage against XSS exposure — an
 * httpOnly cookie set by the backend is the stronger pattern; this is
 * flagged rather than fixed here since it changes the auth flow shape
 * (backend would need to set cookies on login/refresh instead of returning
 * tokens in the JSON body) and is a deliberate scope cut for this starter
 * codebase, not an oversight.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("grmt_access_token");
}

export function setTokens(accessToken: string, refreshToken: string) {
  window.localStorage.setItem("grmt_access_token", accessToken);
  window.localStorage.setItem("grmt_refresh_token", refreshToken);
}

export function clearTokens() {
  window.localStorage.removeItem("grmt_access_token");
  window.localStorage.removeItem("grmt_refresh_token");
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!resp.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `Request failed with status ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail?.error) {
        code = body.detail.error.code || code;
        message = body.detail.error.message || message;
      } else if (body?.detail) {
        message = typeof body.detail === "string" ? body.detail : message;
      }
    } catch {
      // response wasn't JSON — keep the generic message
    }
    throw new ApiError(resp.status, code, message);
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}
