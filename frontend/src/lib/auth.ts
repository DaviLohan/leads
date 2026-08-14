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

/**
 * Mensagem de erro legível a partir da resposta da API.
 *
 * O DRF aninha em profundidade variável: `{"detail": "..."}`, `{"campo": ["..."]}` e, quando
 * o campo é uma lista, `{"campo": {"0": ["..."]}}`. Ler só os dois primeiros formatos fazia
 * o terceiro cair no texto genérico — e "não foi possível" esconde justamente o erro que
 * diria o que corrigir.
 */
export function errorMessage(error: unknown, fallback = "Não foi possível concluir."): string {
  if (!(error instanceof ApiError)) return fallback;
  // Corpo que é só uma string não é mensagem: é resposta não-JSON, tipicamente a página de
  // erro do servidor. Mostrá-la despejaria HTML ou traceback na tela do usuário.
  if (typeof error.body === "string") return fallback;
  return primeiraMensagem(error.body) ?? fallback;
}

function primeiraMensagem(valor: unknown): string | null {
  if (typeof valor === "string") return valor.trim() || null;
  if (Array.isArray(valor)) {
    for (const item of valor) {
      const achado = primeiraMensagem(item);
      if (achado) return achado;
    }
    return null;
  }
  if (valor && typeof valor === "object") {
    const corpo = valor as Record<string, unknown>;
    // `detail` primeiro: é onde o DRF põe a mensagem que já vem pronta para humano.
    if (typeof corpo.detail === "string") return corpo.detail;
    for (const item of Object.values(corpo)) {
      const achado = primeiraMensagem(item);
      if (achado) return achado;
    }
  }
  return null;
}
