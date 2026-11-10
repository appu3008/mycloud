/**
 * Typed fetch wrapper for MyCloud API.
 * - sends session cookie (httpOnly) with every request
 * - attaches the session-scoped CSRF token on mutating methods
 * - 401s surface through onUnauthorized hooks handled in AuthContext
 */

const CSRF_STORAGE_KEY = "mycloud_csrf";

export class ApiError extends Error {
  status: number;
  code: string | undefined;
  detail: unknown;

  constructor(status: number, payload: unknown) {
    const record = (
      payload as
        | { detail?: unknown }
        | null
    )?.detail;
    let code: string | undefined;
    if (Array.isArray(record)) {
      const first = record[0] as { msg?: string } | undefined;
      code = first?.msg;
    } else if (record && typeof record === "object" && "error" in record) {
      code = (record as { error?: string }).error;
    }
    super(`API ${status}${code ? ` (${code})` : ""}`);
    this.status = status;
    this.code = code;
    this.detail = payload;
  }
}

export function getCsrfToken(): string | null {
  return sessionStorage.getItem(CSRF_STORAGE_KEY) ?? localStorage.getItem(CSRF_STORAGE_KEY);
}

export function setCsrfToken(token: string, remember = false) {
  if (remember) {
    localStorage.setItem(CSRF_STORAGE_KEY, token);
  } else {
    sessionStorage.setItem(CSRF_STORAGE_KEY, token);
  }
}

export function clearCsrfToken() {
  sessionStorage.removeItem(CSRF_STORAGE_KEY);
  localStorage.removeItem(CSRF_STORAGE_KEY);
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  json?: any;
  blob?: Blob | ArrayBuffer;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function api<T>(
  path: string,
  { method = "GET", json, blob, headers = {}, signal }: RequestOptions = {},
): Promise<T> {
  const request = new Request(`/api${path}`, {
    method,
    credentials: "include",
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" && getCsrfToken() ? { "X-CSRF-Token": getCsrfToken()! } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : blob !== undefined ? blob : undefined,
    signal,
  });

  const response = await fetch(request);
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = await response.text();
    }
    throw new ApiError(response.status, payload);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.blob()) as unknown as T;
}

/** Stream a File through the resumable chunked upload API. */
export async function uploadFileResumable(
  file: File,
  callbacks: {
    onReserved?: (uploadId: string, totalChunks: number) => void;
    onChunkDone?: (done: number, total: number) => void;
    signal?: AbortSignal;
  } = {},
): Promise<{ fileId: string; name: string }> {
  const oneMiB = 1024 * 1024;
  const reserved = await api<{
    upload_id: string;
    chunk_size: number;
    total_chunks: number;
    state: string;
  }>("/v1/uploads", {
    method: "POST",
    json: {
      filename: file.name,
      size_bytes: file.size,
      chunk_size_mb: Math.max(1, Math.min(16, Math.ceil(file.size / oneMiB / 64) || 1)),
    },
    signal: callbacks.signal,
  });
  callbacks.onReserved?.(reserved.upload_id, reserved.total_chunks);

  const total = reserved.total_chunks;
  for (let number = 1; number <= total; number += 1) {
    const start = (number - 1) * reserved.chunk_size;
    const end = Math.min(file.size, start + reserved.chunk_size);
    const chunkBuffer = await file.slice(start, end).arrayBuffer();
    const hashHex = await bufferToHex(await crypto.subtle.digest("SHA-256", chunkBuffer));
    await api(`/v1/uploads/${reserved.upload_id}/chunks/${number}`, {
      method: "PUT",
      blob: chunkBuffer,
      headers: { "X-Chunk-Sha256": hashHex },
      signal: callbacks.signal,
    });
    callbacks.onChunkDone?.(number, total);
  }

  const completed = await api<{
    id: string;
    name: string;
    size_bytes: number;
    mime_type: string;
  }>(`/v1/uploads/${reserved.upload_id}/complete`, { method: "POST", json: {} });
  return { fileId: completed.id, name: completed.name };
}

async function bufferToHex(buffer: ArrayBuffer): Promise<string> {
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function downloadContent(fileId: string, filename: string, eTag?: string) {
  const url = `/api/v1/files/${fileId}/content`;
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  void eTag;
}
