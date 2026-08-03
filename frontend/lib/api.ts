import type { ApiErrorBody } from "./types";
import { authHeaders } from "./auth-store";

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

const JSON_HEADERS = { "Content-Type": "application/json" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
    ...authHeaders(),
  };
  const response = await fetch(path, { ...init, headers });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json() : null;

  if (!response.ok) {
    const body = payload as ApiErrorBody | null;
    const errorPayload = body?.error;
    throw new ApiError(
      response.status,
      errorPayload?.code ?? "http_error",
      errorPayload?.message ?? `请求失败（HTTP ${response.status}）`,
      errorPayload?.request_id,
    );
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, string | number | undefined>) => {
    const url = new URL(path, window.location.origin);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
      }
    }
    return request<T>(url.pathname + url.search);
  },
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
