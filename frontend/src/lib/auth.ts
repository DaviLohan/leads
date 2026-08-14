/**
 * Autenticação no cliente.
 *
 * Não guarda token nenhum: a sessão vive num cookie HTTPOnly que o JavaScript não enxerga
 * (ADR-0005). "Estar logado" é simplesmente o que `GET /auth/me/` responde.
 */

import { ApiError, apiFetch } from "./api";

export type Organization = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
};

export type Membership = {
  id: string;
  organization: Organization;
  role: string;
  is_active: boolean;
  joined_at: string;
};

export type Me = {
  user: { id: string; email: string; full_name: string };
  organization: Organization | null;
  role: string | null;
  memberships: Membership[];
};

export const ROLE_LABELS: Record<string, string> = {
  OWNER: "Proprietário",
  ADMIN: "Administrador",
  MANAGER: "Gestor",
  SALES: "Comercial",
  VIEWER: "Leitor",
};

/** Garante o cookie `csrftoken` antes de qualquer requisição que altere estado. */
export async function primeCsrf(): Promise<void> {
  await apiFetch("/auth/csrf/");
}

export async function login(email: string, password: string): Promise<Me> {
  await primeCsrf();
  return apiFetch<Me>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout/", { method: "POST" });
}

/** Devolve `null` quando não há sessão — 401 aqui é resposta esperada, não erro. */
export async function getMe(): Promise<Me | null> {
  try {
    return await apiFetch<Me>("/auth/me/");
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return null;
    }
    throw error;
  }
}

/** Mensagem de erro legível a partir da resposta da API. */
export function errorMessage(error: unknown, fallback = "Não foi possível concluir."): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object") {
    const body = error.body as Record<string, unknown>;
    if (typeof body.detail === "string") return body.detail;
    const first = Object.values(body)[0];
    if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  }
  return fallback;
}
