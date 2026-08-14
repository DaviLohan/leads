/** Chamadas à API, por recurso. Uma função por coisa que a tela precisa. */

import { apiFetch } from "./api";
import type {
  Analise,
  Anotacao,
  Busca,
  Estado,
  Funil,
  Interacao,
  JobDeBusca,
  Lacunas,
  Lead,
  Municipio,
  Oportunidade,
  Pagina,
  Pontuacao,
  Supressao,
} from "./tipos";

function qs(params: Record<string, string | number | undefined>): string {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== "") busca.set(chave, String(valor));
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

// --- Geografia ---------------------------------------------------------------

export const listarEstados = () => apiFetch<Pagina<Estado>>("/geography/states/?page_size=30");

export const listarMunicipios = (params: { uf?: string; q?: string } = {}) =>
  apiFetch<Pagina<Municipio>>(`/geography/cities/${qs({ ...params, page_size: 200 })}`);

// --- Análise -----------------------------------------------------------------

export const listarPontuacoes = (pagina = 1) =>
  apiFetch<Pagina<Pontuacao>>(`/analysis/scores/${qs({ page: pagina })}`);

export const pontuacaoDaEmpresa = (empresa: string) =>
  apiFetch<Pagina<Pontuacao>>(`/analysis/scores/${qs({ company: empresa })}`);

export const listarOportunidades = (params: { company?: string; status?: string } = {}) =>
  apiFetch<Pagina<Oportunidade>>(`/analysis/opportunities/${qs({ ...params, page_size: 100 })}`);

export const listarAnalises = (params: { company?: string } = {}) =>
  apiFetch<Pagina<Analise>>(`/analysis/scans/${qs(params)}`);

export const reanalisar = (empresa: string) =>
  apiFetch<{ detail: string }>(`/analysis/scans/companies/${empresa}/`, { method: "POST" });

// --- Descoberta --------------------------------------------------------------

export const listarBuscas = () => apiFetch<Pagina<Busca>>("/discovery/searches/");

export const buscaPorId = (id: string) => apiFetch<Busca>(`/discovery/searches/${id}/`);

export const jobsDaBusca = (id: string) =>
  apiFetch<Pagina<JobDeBusca>>(`/discovery/searches/${id}/jobs/?page_size=100`);

export type Criterios = {
  uf?: string[];
  city_ids?: string[];
  category_ids: string[];
  provider_slugs: string[];
};

export const prever = (criteria: Criterios) =>
  apiFetch<{ cities: number; categories: number; providers: number; estimated_jobs: number }>(
    "/discovery/searches/preview/",
    { method: "POST", body: JSON.stringify({ criteria }) },
  );

export const criarBusca = (name: string, criteria: Criterios) =>
  apiFetch<Busca>("/discovery/searches/", {
    method: "POST",
    body: JSON.stringify({ name, criteria }),
  });

export const cancelarBusca = (id: string) =>
  apiFetch<Busca>(`/discovery/searches/${id}/cancel/`, { method: "POST" });

// --- CRM ---------------------------------------------------------------------

export const listarFunis = () => apiFetch<Pagina<Funil>>("/crm/pipelines/");

export const listarLeads = (params: { stage?: string; page?: number } = {}) =>
  apiFetch<Pagina<Lead>>(`/crm/leads/${qs(params)}`);

export const leadPorId = (id: string) => apiFetch<Lead>(`/crm/leads/${id}/`);

export const criarLead = (empresa: string) =>
  apiFetch<Lead>("/crm/leads/", { method: "POST", body: JSON.stringify({ company: empresa }) });

export const moverLead = (id: string, estagio: string, note = "") =>
  apiFetch<Lead>(`/crm/leads/${id}/move/`, {
    method: "POST",
    body: JSON.stringify({ stage: estagio, note }),
  });

export const historicoDoLead = (id: string) =>
  apiFetch<Pagina<Interacao>>(`/crm/leads/${id}/interactions/?page_size=100`);

export const registrarInteracao = (id: string, dados: Partial<Interacao>) =>
  apiFetch<Interacao>(`/crm/leads/${id}/interactions/`, {
    method: "POST",
    body: JSON.stringify(dados),
  });

export const anotacoesDoLead = (id: string) =>
  apiFetch<Pagina<Anotacao>>(`/crm/leads/${id}/notes/?page_size=100`);

export const anotar = (id: string, body: string) =>
  apiFetch<Anotacao>(`/crm/leads/${id}/notes/`, { method: "POST", body: JSON.stringify({ body }) });

export const listarSupressoes = () => apiFetch<Pagina<Supressao>>("/crm/suppressions/");

export const suprimir = (dados: {
  identifier_kind: string;
  identifier_value: string;
  reason: string;
}) =>
  apiFetch<Supressao & { leads_encerrados: number }>("/crm/suppressions/", {
    method: "POST",
    body: JSON.stringify(dados),
  });

// --- Derivações --------------------------------------------------------------

/**
 * Traduz uma análise nos cinco sinais da barra de lacunas.
 *
 * `true` significa **falta** — é a inversão que dá sentido ao produto. Sem análise, tudo é
 * `null`: "ainda não sei" nunca vira "não tem", pela mesma razão que o backend não deixa.
 */
export function lacunasDe(analise: Analise | undefined, temSite: boolean): Lacunas {
  if (!analise) {
    return {
      site: temSite ? false : null,
      celular: null,
      contato: null,
      agenda: null,
      seguro: null,
    };
  }
  if (analise.status !== "OK") {
    // Site que não responde é lacuna em tudo: na prática a empresa não tem presença.
    return { site: true, celular: true, contato: true, agenda: true, seguro: true };
  }
  return {
    site: false,
    celular: !analise.has_viewport,
    contato: !analise.has_contact_form && !analise.has_whatsapp,
    agenda: !analise.has_booking,
    seguro: !analise.is_https,
  };
}
