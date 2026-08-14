/** Os tipos que a API devolve. Espelham os serializers do backend. */

export type Pagina<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type Estado = { id: string; uf: string; name: string; region: string };
export type Categoria = { id: string; slug: string; name: string };
export type Municipio = { id: string; name: string; uf: string; ibge_code: string };

export type Achado = {
  id: string;
  code: string;
  code_label: string;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH";
  detail: string;
};

export type Analise = {
  id: string;
  company: string;
  company_name: string;
  final_url: string;
  status: "OK" | "UNREACHABLE" | "BLOCKED" | "ERROR";
  http_status: number | null;
  is_https: boolean;
  response_time_ms: number | null;
  title: string;
  has_viewport: boolean;
  has_contact_form: boolean;
  has_whatsapp: boolean;
  has_booking: boolean;
  has_cart: boolean;
  error_detail: string;
  scanned_at: string;
  findings: Achado[];
};

export type Oportunidade = {
  id: string;
  company: string;
  company_name: string;
  type_code: string;
  type_name: string;
  type_description: string;
  status: "OPEN" | "RESOLVED" | "DISMISSED";
  confidence: string;
  detected_at: string;
};

export type Parcela = { rule_code: string; points: number; reason: string };

export type Pontuacao = {
  id: string;
  company: string;
  company_name: string;
  value: number;
  version: string;
  computed_at: string;
  components: Parcela[];
};

export type Busca = {
  id: string;
  name: string;
  criteria: Record<string, unknown>;
  status: "PENDING" | "RUNNING" | "PARTIALLY_COMPLETED" | "COMPLETED" | "FAILED" | "CANCELLED";
  progress: number;
  job_count: number;
  created_at: string;
  finished_at: string | null;
};

export type JobDeBusca = {
  id: string;
  city: string;
  uf: string;
  category: string;
  provider: string;
  status: string;
  found_count: number;
  new_count: number;
  duplicate_count: number;
  review_count: number;
  error_count: number;
  attempts: number;
  last_error: string;
};

export type Estagio = {
  id: string;
  code: string;
  name: string;
  position: number;
  is_terminal: boolean;
  is_won: boolean;
  lead_count: number;
};

export type Funil = { id: string; name: string; is_default: boolean; stages: Estagio[] };

export type Lead = {
  id: string;
  company: string;
  company_name: string;
  stage: string;
  stage_code: string;
  stage_name: string;
  owner: string | null;
  owner_email: string | null;
  score_snapshot: number;
  current_score: number | null;
  last_contacted_at: string | null;
  next_action_at: string | null;
  created_at: string;
};

export type Interacao = {
  id: string;
  kind: string;
  kind_label: string;
  description: string;
  outcome: string;
  next_action: string;
  next_action_at: string | null;
  occurred_at: string;
  author_name: string | null;
};

export type Anotacao = {
  id: string;
  body: string;
  author_email: string | null;
  created_at: string;
};

export type Supressao = {
  id: string;
  identifier_kind: "PHONE" | "EMAIL" | "DOMAIN" | "TAX_ID" | "COMPANY";
  identifier_value: string;
  reason: string;
  created_at: string;
};

/** Os cinco sinais que a barra de lacunas mostra. `null` = ainda não verificado. */
export type Lacunas = {
  site: boolean | null;
  celular: boolean | null;
  contato: boolean | null;
  agenda: boolean | null;
  seguro: boolean | null;
};

export const ROTULO_LACUNA: Record<keyof Lacunas, string> = {
  site: "site",
  celular: "celular",
  contato: "contato",
  agenda: "agenda",
  seguro: "https",
};
