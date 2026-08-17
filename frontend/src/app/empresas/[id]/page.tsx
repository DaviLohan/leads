"use client";

import { Building2, Globe, Mail, MapPin, RefreshCw, Target, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { BarraDeLacunas } from "@/components/lacunas";
import { Ausente, BotaoWhatsApp, Telefone } from "@/components/telefone";
import { useAviso } from "@/components/ui/aviso";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Etiqueta, Score } from "@/components/ui/etiqueta";
import { Cartao, Erro, Esqueleto, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import {
  criarLead,
  empresaPorId,
  lacunasDe,
  listarAnalises,
  listarOportunidades,
  origensDaEmpresa,
  pontuacaoDaEmpresa,
  reanalisar,
} from "@/lib/recursos";
import type { Analise, EmpresaDetalhe, Oportunidade, Pontuacao, Procedencia } from "@/lib/tipos";

/**
 * A ficha da empresa: tudo que se precisa saber antes de discar.
 *
 * A ordem é a de uma conversa de venda, e **contato vem primeiro** — telefone, WhatsApp,
 * e-mail e endereço no topo, nunca atrás de "informações técnicas". Depois o diagnóstico: o
 * que falta, o que dá para vender, e a evidência de cada afirmação.
 *
 * As abas separam três perguntas diferentes que antes disputavam a mesma coluna: *o que dá
 * para vender* (oportunidades), *o que a análise viu* (diagnóstico) e *de onde veio o dado*
 * (procedência). Contato fica fora de aba: é o que se busca com mais frequência.
 */

const ABAS = [
  { chave: "oportunidades", rotulo: "Oportunidades" },
  { chave: "diagnostico", rotulo: "Diagnóstico do site" },
  { chave: "origem", rotulo: "Origem dos dados" },
] as const;

type Aba = (typeof ABAS)[number]["chave"];

export default function DetalheDaEmpresa() {
  const { id } = useParams<{ id: string }>();
  const avisar = useAviso();
  const [empresa, setEmpresa] = useState<EmpresaDetalhe | null>(null);
  const [pontuacao, setPontuacao] = useState<Pontuacao | null>(null);
  const [analise, setAnalise] = useState<Analise | null>(null);
  const [oportunidades, setOportunidades] = useState<Oportunidade[]>([]);
  const [origens, setOrigens] = useState<Procedencia[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("oportunidades");

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    return Promise.all([
      empresaPorId(id),
      pontuacaoDaEmpresa(id),
      listarAnalises({ company: id }),
      listarOportunidades({ company: id, status: "OPEN" }),
      origensDaEmpresa(id),
    ])
      .then(([e, p, a, o, f]) => {
        setEmpresa(e);
        setPontuacao(p.results[0] ?? null);
        setAnalise(a.results[0] ?? null);
        setOportunidades(o.results);
        setOrigens(f.results);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar a empresa.")))
      .finally(() => setCarregando(false));
  }, [id]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  if (carregando) {
    return (
      <Casca>
        <div className="space-y-6">
          <Esqueleto className="h-8 w-72" />
          <Esqueleto className="h-24 w-full" />
          <Esqueleto className="h-64 w-full" />
        </div>
      </Casca>
    );
  }

  if (erro || !empresa) {
    return (
      <Casca>
        <Erro mensagem={erro ?? "Empresa não encontrada."} aoTentarNovamente={carregar} />
      </Casca>
    );
  }

  const lacunas = lacunasDe(analise ?? undefined, Boolean(analise));
  const endereco = empresa.addresses.find((e) => e.is_primary) ?? empresa.addresses[0];

  return (
    <Casca>
      <CabecalhoDaPagina
        voltar={{ href: "/empresas", rotulo: "Empresas" }}
        titulo={empresa.name}
        descricao={[empresa.category, empresa.city && `${empresa.city} — ${empresa.uf}`]
          .filter(Boolean)
          .join(" · ")}
        acao={
          <>
            <Botao
              variante="secundaria"
              Icone={RefreshCw}
              onClick={async () => {
                try {
                  await reanalisar(id);
                  avisar("Análise enfileirada. Atualize em alguns segundos.");
                } catch (e) {
                  avisar(errorMessage(e, "Não foi possível reanalisar."), "erro");
                }
              }}
            >
              Reanalisar site
            </Botao>
            {empresa.lead_id ? (
              <Link href={`/leads/${empresa.lead_id}`}>
                <Botao variante="primaria" Icone={Target}>
                  No funil: {empresa.lead_stage_name ?? "ver"}
                </Botao>
              </Link>
            ) : (
              <Botao
                variante="primaria"
                Icone={Target}
                onClick={async () => {
                  try {
                    const lead = await criarLead(id);
                    setEmpresa((atual) =>
                      atual
                        ? { ...atual, lead_id: lead.id, lead_stage_name: lead.stage_name }
                        : atual,
                    );
                    avisar("Lead criado. Está na aba Leads.");
                  } catch (e) {
                    avisar(errorMessage(e, "Não foi possível criar o lead."), "erro");
                  }
                }}
              >
                Adicionar ao CRM
              </Botao>
            )}
          </>
        }
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0 space-y-6">
          {/* Contato fora de aba: é o dado mais buscado da tela. */}
          <Cartao padding={false}>
            <div className="border-linha flex h-12 items-center border-b px-4">
              <h2 className="rotulo-secao">Contato</h2>
            </div>
            <dl className="grid gap-x-8 gap-y-4 p-4 sm:grid-cols-2">
              <Dado rotulo="Telefone">
                <Telefone valor={empresa.phone} />
              </Dado>
              <Dado rotulo="WhatsApp confirmado">
                <BotaoWhatsApp numero={empresa.whatsapp} rotulo="Abrir conversa" />
              </Dado>
              <Dado rotulo="E-mail" Icone={Mail}>
                {empresa.email ? (
                  <a href={`mailto:${empresa.email}`} className="text-tinta hover:text-acao">
                    {empresa.email}
                  </a>
                ) : (
                  <Ausente />
                )}
              </Dado>
              <Dado rotulo="Site" Icone={Globe}>
                {empresa.website ? (
                  <a
                    href={empresa.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-tinta hover:text-acao break-all"
                  >
                    {empresa.website.replace(/^https?:\/\//, "")}
                  </a>
                ) : empresa.website_status === "NOT_FOUND" ? (
                  <Etiqueta tom="lacuna">não identificado nas fontes</Etiqueta>
                ) : (
                  <Ausente titulo="Ainda não verificado" />
                )}
              </Dado>
              <Dado rotulo="Endereço" Icone={MapPin} largo>
                {endereco ? (
                  <span className="text-tinta">
                    {[endereco.street, endereco.number, endereco.district]
                      .filter(Boolean)
                      .join(", ")}
                    {endereco.street && " — "}
                    {endereco.city_name}/{endereco.uf}
                  </span>
                ) : (
                  <Ausente />
                )}
              </Dado>
              {empresa.social_profiles.length > 0 && (
                <Dado rotulo="Redes" largo>
                  <span className="flex flex-wrap gap-3">
                    {empresa.social_profiles.map((perfil) => (
                      <a
                        key={perfil.id}
                        href={perfil.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-tinta hover:text-acao"
                      >
                        {perfil.network_label}
                      </a>
                    ))}
                  </span>
                </Dado>
              )}
            </dl>
          </Cartao>

          {/* Abas */}
          <div>
            <div className="border-linha mb-4 flex gap-1 border-b" role="tablist">
              {ABAS.map(({ chave, rotulo }) => (
                <button
                  key={chave}
                  role="tab"
                  aria-selected={aba === chave}
                  onClick={() => setAba(chave)}
                  className={`text-corpo -mb-px border-b-2 px-3 py-2 font-medium transition-colors ${
                    aba === chave
                      ? "border-acao text-tinta"
                      : "text-tinta-fraca hover:text-tinta border-transparent"
                  }`}
                >
                  {rotulo}
                </button>
              ))}
            </div>

            {aba === "oportunidades" &&
              (oportunidades.length === 0 ? (
                <Vazio
                  titulo="Nenhuma oportunidade aberta."
                  descricao="Oportunidade só aparece depois que a análise roda — ausência de dado não vira diagnóstico."
                  Icone={Target}
                />
              ) : (
                <ul className="space-y-2">
                  {oportunidades.map((o) => (
                    <li key={o.id} className="border-linha bg-papel-alto rounded-md border p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="text-tinta font-medium">{o.type_name}</h3>
                          <p className="text-apoio text-tinta-fraca mt-1">{o.type_description}</p>
                        </div>
                        <Etiqueta tom="lacuna">oportunidade</Etiqueta>
                      </div>
                    </li>
                  ))}
                </ul>
              ))}

            {aba === "diagnostico" &&
              (!analise ? (
                <Vazio
                  titulo="Site ainda não verificado."
                  descricao="Enquanto a análise não roda, a resposta honesta é 'ainda não sei'."
                  Icone={Globe}
                />
              ) : analise.status !== "OK" ? (
                <Cartao>
                  <div className="flex items-start gap-3">
                    <TriangleAlert size={16} className="text-perdido mt-0.5 shrink-0" aria-hidden />
                    <div>
                      <p className="text-tinta font-medium">{rotuloDaAnalise(analise.status)}</p>
                      <p className="text-apoio text-tinta-fraca mt-1">{analise.error_detail}</p>
                    </div>
                  </div>
                </Cartao>
              ) : (
                <Cartao>
                  <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                    <Dado rotulo="Endereço final">
                      <span className="dados text-apoio truncate">{analise.final_url}</span>
                    </Dado>
                    <Dado rotulo="HTTP">
                      <span className="dados">{analise.http_status}</span>
                    </Dado>
                    <Dado rotulo="Resposta">
                      <span className="dados">{analise.response_time_ms} ms</span>
                    </Dado>
                  </dl>
                  {analise.findings.length > 0 && (
                    <ul className="border-linha mt-4 space-y-2 border-t pt-4">
                      {analise.findings.map((f) => (
                        <li key={f.id} className="flex items-start gap-3">
                          <Etiqueta tom={f.severity === "HIGH" ? "lacuna" : "neutro"}>
                            {f.severity === "HIGH" ? "alta" : f.severity.toLowerCase()}
                          </Etiqueta>
                          <span className="text-apoio text-tinta-media">
                            {f.detail || f.code_label}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Cartao>
              ))}

            {aba === "origem" &&
              (origens.length === 0 ? (
                <Vazio titulo="Sem procedência registrada." Icone={Building2} />
              ) : (
                <Cartao>
                  <ul className="divide-linha divide-y">
                    {origens.map((origem) => (
                      <li
                        key={origem.id}
                        className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-2.5 first:pt-0 last:pb-0"
                      >
                        <span className="text-tinta w-40 font-medium">{origem.provider_name}</span>
                        <span className="dados text-apoio text-tinta-media">
                          {origem.external_id}
                        </span>
                        <span className="text-legenda text-tinta-fraca ml-auto">
                          coletado em {new Date(origem.collected_at).toLocaleDateString("pt-BR")} ·
                          confiança {origem.confidence}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Cartao>
              ))}
          </div>
        </div>

        {/* Coluna de prioridade: score, o que falta, e o cálculo. */}
        <aside className="space-y-4 lg:sticky lg:top-8">
          <Cartao>
            <div className="flex items-baseline gap-2">
              <Score valor={pontuacao?.value ?? null} tamanho="lg" />
              <span className="text-apoio text-tinta-fraca">de 100</span>
            </div>
            <p className="text-legenda text-tinta-fraca mt-1">Prioridade de abordagem</p>

            {pontuacao && pontuacao.components.length > 0 && (
              <ul className="border-linha mt-4 space-y-2 border-t pt-4">
                {pontuacao.components.map((c) => (
                  <li key={c.rule_code} className="flex gap-3">
                    <span
                      className={`dados text-apoio w-8 shrink-0 text-right font-semibold ${
                        c.points > 0 ? "text-lacuna" : "text-tinta-fraca"
                      }`}
                    >
                      {c.points > 0 ? `+${c.points}` : c.points}
                    </span>
                    <span className="text-apoio text-tinta-media">{c.reason}</span>
                  </li>
                ))}
              </ul>
            )}
            {pontuacao && (
              <p className="dados text-legenda text-tinta-fraca/70 mt-4">
                regras {pontuacao.version}
              </p>
            )}
          </Cartao>

          <Cartao>
            <h2 className="rotulo-secao mb-3">O que falta</h2>
            <BarraDeLacunas lacunas={lacunas} rotulos />
            {!analise && (
              <p className="text-legenda text-tinta-fraca mt-3">
                O site desta empresa ainda não foi verificado.
              </p>
            )}
          </Cartao>
        </aside>
      </div>
    </Casca>
  );
}

function Dado({
  rotulo,
  children,
  Icone,
  largo = false,
}: {
  rotulo: string;
  children: React.ReactNode;
  Icone?: typeof Mail;
  largo?: boolean;
}) {
  return (
    <div className={`min-w-0 ${largo ? "sm:col-span-2" : ""}`}>
      <dt className="text-legenda text-tinta-fraca flex items-center gap-1.5">
        {Icone && <Icone size={12} aria-hidden />}
        {rotulo}
      </dt>
      <dd className="text-corpo mt-1">{children}</dd>
    </div>
  );
}

function rotuloDaAnalise(status: Analise["status"]): string {
  return (
    {
      UNREACHABLE: "Fora do ar",
      // Recusado pelo guard de SSRF: é evento de segurança, e a tela não o disfarça de
      // indisponibilidade — pelo mesmo motivo que o backend usa status separado.
      BLOCKED: "Endereço recusado",
      ERROR: "Erro na análise",
      OK: "Analisado",
    }[status] ?? status
  );
}
