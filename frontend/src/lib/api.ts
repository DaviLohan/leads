/**
 * Cliente HTTP da API.
 *
 * A autenticação é por cookie de sessão HTTPOnly (ADR-0005), então:
 * - as requisições vão com `credentials: "include"`;
 * - as que alteram estado carregam o token CSRF no header.
 *
 * As URLs são sempre relativas: o rewrite do Next mantém tudo na mesma origem.
 */

export const API_BASE = "/api/v1";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`Falha na API (${status})`);
    this.name = "ApiError";
  }
}

/** Lê um cookie pelo nome. Devolve `null` quando não existe ou fora do browser. */
export function readCookie(name: string, cookieString?: string): string | null {
  const source = cookieString ?? (typeof document === "undefined" ? "" : document.cookie);
  for (const part of source.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() === name) {
      return decodeURIComponent(part.slice(separator + 1).trim());
    }
  }
  return null;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  const isJson = response.headers.get("content-type")?.includes("application/json") ?? false;
  const body: unknown = isJson ? await response.json() : await response.text();

  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
