"use client";

import { ExternalLink, Kanban, List, Target } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { Ausente, BotaoWhatsApp, Telefone } from "@/components/telefone";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { EtiquetaDeEstagio, Score } from "@/components/ui/etiqueta";
import { Erro, EsqueletoDeTabela, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import { listarFunis, listarLeads } from "@/lib/recursos";
import type { Estagio, Lead } from "@/lib/tipos";

/**
 * Leads — a fila de trabalho comercial.
 *
 * Uma seção, duas vistas da mesma coisa: **lista** para trabalhar (telefone na linha, ordem de
 * prioridade) e **funil** para enxergar onde está cada conversa. Separá-las em dois itens de
 * menu criaria dois lugares para procurar o mesmo lead.
 *
 * A lista é o padrão de propósito: é ela que responde "para quem eu ligo agora". O Kanban
 * responde "como está o mês", que é uma pergunta de fim de semana, não de terça de manhã.
 */
export default function Leads() {
  return (
    <Casca>
      <Suspense fallback={<EsqueletoDeTabela />}>
        <Conteudo />
      </Suspense>
    </Casca>
  );
}

function Conteudo() {
  const router = useRouter();
  const parametros = useSearchParams();
  const vista = parametros.get("vista") === "funil" ? "funil" : "lista";
  const estagioFiltrado = parametros.get("stage") ?? "";

  const [estagios, setEstagios] = useState<Estagio[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    // No funil, os leads vêm todos: são as colunas inteiras que precisam ser preenchidas.
    const filtro =
      vista === "funil" ? { page_size: 200 } : estagioFiltrado ? { stage: estagioFiltrado } : {};
    return Promise.all([listarFunis(), listarLeads(filtro)])
      .then(([f, l]) => {
        setEstagios(f.results[0]?.stages ?? []);
        setLeads(l.results);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar os leads.")))
      .finally(() => setCarregando(false));
  }, [estagioFiltrado, vista]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function irPara(proximo: { vista?: string; stage?: string }) {
    const busca = new URLSearchParams();
    const v = proximo.vista ?? vista;
    const s = proximo.stage ?? estagioFiltrado;
    if (v === "funil") busca.set("vista", "funil");
    if (s && v !== "funil") busca.set("stage", s);
    router.replace(busca.size ? `/leads?${busca}` : "/leads");
  }

  const total = estagios.reduce((soma, e) => soma + e.lead_count, 0);

  return (
    <>
      <CabecalhoDaPagina
        titulo="Leads"
        descricao="Quem está na fila, em que ponto da conversa, e o que fazer a seguir."
        contador={`${total} ${total === 1 ? "lead" : "leads"}`}
        acao={<AlternadorDeVista vista={vista} aoTrocar={(v) => irPara({ vista: v })} />}
      />

      {erro && <Erro mensagem={erro} aoTentarNovamente={carregar} className="mb-4" />}

      {carregando ? (
        <EsqueletoDeTabela linhas={6} colunas={6} />
      ) : total === 0 ? (
        <Vazio
          titulo="Nenhum lead ainda."
          descricao="Escolha empresas com oportunidade aberta e mande para o funil."
          Icone={Target}
          acao={
            <Link href="/empresas">
              <Botao variante="primaria">Ir para Empresas</Botao>
            </Link>
          }
        />
      ) : vista === "funil" ? (
        <Funil estagios={estagios} leads={leads} />
      ) : (
        <>
          <FiltroDeEstagio
            estagios={estagios}
            selecionado={estagioFiltrado}
            aoSelecionar={(id) => irPara({ stage: id === estagioFiltrado ? "" : id })}
          />
          {leads.length === 0 ? (
            <Vazio titulo="Nenhum lead neste estágio." Icone={Target} />
          ) : (
            <TabelaDeLeads leads={leads} />
          )}
        </>
      )}
    </>
  );
}

/** Alternador de vista: dois botões num trilho, o ativo com fundo sólido. */
function AlternadorDeVista({ vista, aoTrocar }: { vista: string; aoTrocar: (v: string) => void }) {
  const opcoes = [
    { valor: "lista", rotulo: "Lista", Icone: List },
    { valor: "funil", rotulo: "Funil", Icone: Kanban },
  ];
  return (
    <div className="border-linha bg-papel-alto flex rounded-sm border p-0.5" role="tablist">
      {opcoes.map(({ valor, rotulo, Icone }) => (
        <button
          key={valor}
          role="tab"
          aria-selected={vista === valor}
          onClick={() => aoTrocar(valor)}
          className={`text-apoio inline-flex h-8 items-center gap-1.5 rounded-sm px-3 font-medium transition-colors ${
            vista === valor ? "bg-papel-fundo text-tinta" : "text-tinta-fraca hover:text-tinta"
          }`}
        >
          <Icone size={14} aria-hidden />
          {rotulo}
        </button>
      ))}
    </div>
  );
}

/** Filtro por estágio na vista de lista: pílulas com contagem. */
function FiltroDeEstagio({
  estagios,
  selecionado,
  aoSelecionar,
}: {
  estagios: Estagio[];
  selecionado: string;
  aoSelecionar: (id: string) => void;
}) {
  return (
    <div className="mb-4 flex flex-wrap gap-1.5">
      {estagios.map((estagio) => {
        const ativo = selecionado === estagio.id;
        return (
          <button
            key={estagio.id}
            onClick={() => aoSelecionar(estagio.id)}
            aria-pressed={ativo}
            className={`text-apoio inline-flex h-8 items-center gap-1.5 rounded-sm border px-2.5 font-medium transition-colors ${
              ativo
                ? "border-acao bg-acao-fraca text-acao"
                : "border-linha bg-papel-alto text-tinta-media hover:border-linha-forte"
            }`}
          >
            {estagio.name}
            <span className="dados text-legenda text-tinta-fraca">{estagio.lead_count}</span>
          </button>
        );
      })}
    </div>
  );
}

/** A tabela de trabalho: empresa, contato, oportunidade, prioridade, situação, próxima ação. */
function TabelaDeLeads({ leads }: { leads: Lead[] }) {
  return (
    <div className="border-linha bg-papel-alto overflow-x-auto rounded-md border">
      <table className="text-corpo w-full min-w-[60rem] border-collapse">
        <colgroup>
          <col />
          <col style={{ width: "11rem" }} />
          <col style={{ width: "7rem" }} />
          <col style={{ width: "12rem" }} />
          <col style={{ width: "5.5rem" }} />
          <col style={{ width: "9rem" }} />
          <col style={{ width: "8rem" }} />
          <col style={{ width: "3rem" }} />
        </colgroup>
        <thead className="bg-papel-alto sticky top-0 z-[var(--z-sticky)]">
          <tr className="border-linha border-b">
            {[
              "Empresa",
              "Telefone",
              "WhatsApp",
              "Oportunidade",
              "Score",
              "Estágio",
              "Último contato",
              "",
            ].map((rotulo, i) => (
              <th
                key={rotulo || i}
                scope="col"
                className={`text-legenda text-tinta-fraca h-10 px-3 text-left font-semibold tracking-wide uppercase ${
                  rotulo === "Score" ? "text-right" : ""
                }`}
              >
                {rotulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-linha divide-y">
          {leads.map((lead) => (
            <tr key={lead.id} className="group hover:bg-papel/70 h-14 transition-colors">
              <td className="min-w-0 px-3 py-2">
                <Link
                  href={`/leads/${lead.id}`}
                  className="text-tinta hover:text-acao block truncate font-medium"
                >
                  {lead.company_name}
                </Link>
                {lead.city && (
                  <span className="text-legenda text-tinta-fraca block truncate">
                    {lead.city}/{lead.uf}
                  </span>
                )}
              </td>
              <td className="px-3">
                <Telefone valor={lead.phone} />
              </td>
              <td className="px-3">
                <BotaoWhatsApp numero={lead.whatsapp} />
              </td>
              <td className="text-lacuna text-apoio truncate px-3">
                {lead.opportunities.map((o) => o.name).join(" · ") || <Ausente />}
              </td>
              <td className="px-3 text-right">
                <Score valor={lead.score_snapshot} />
              </td>
              <td className="px-3">
                <EtiquetaDeEstagio codigo={lead.stage_code} nome={lead.stage_name} />
              </td>
              <td className="text-tinta-fraca text-apoio px-3 whitespace-nowrap">
                {lead.last_contacted_at ? data(lead.last_contacted_at) : "sem contato"}
              </td>
              <td className="px-3 text-right">
                <Link
                  href={`/leads/${lead.id}`}
                  title={`Abrir ${lead.company_name}`}
                  aria-label={`Abrir ${lead.company_name}`}
                  className="text-tinta-fraca hover:text-acao hover:bg-papel-fundo inline-flex rounded-sm p-1.5 opacity-0 transition-all group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <ExternalLink size={14} aria-hidden />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * O funil em colunas.
 *
 * Rolagem horizontal em vez de espremer sete estágios na largura da tela — coluna de 15rem é
 * o mínimo para o nome da empresa e o telefone caberem, e é o telefone que faz o cartão valer
 * alguma coisa. Cada cartão mostra quatro dados: empresa, telefone, score e último contato.
 * Mais que isso vira parágrafo, e ninguém lê parágrafo em Kanban.
 */
function Funil({ estagios, leads }: { estagios: Estagio[]; leads: Lead[] }) {
  return (
    <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
      {estagios.map((estagio) => {
        const doEstagio = leads.filter((l) => l.stage === estagio.id);
        return (
          <section key={estagio.id} className="w-60 shrink-0" aria-label={estagio.name}>
            <header className="mb-2 flex items-center justify-between px-1">
              <h2 className="text-apoio text-tinta font-semibold">{estagio.name}</h2>
              <span className="dados text-legenda text-tinta-fraca">{estagio.lead_count}</span>
            </header>
            <div
              className={`space-y-2 rounded-md p-2 ${
                estagio.is_won ? "bg-ganho-fraca/50" : "bg-papel-fundo/60"
              }`}
            >
              {doEstagio.length === 0 ? (
                <p className="text-legenda text-tinta-fraca/70 px-1 py-3 text-center">vazio</p>
              ) : (
                doEstagio.map((lead) => (
                  <Link
                    key={lead.id}
                    href={`/leads/${lead.id}`}
                    className="border-linha bg-papel-alto hover:border-linha-forte block rounded-sm border p-2.5 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-apoio text-tinta line-clamp-2 font-medium">
                        {lead.company_name}
                      </span>
                      <Score valor={lead.score_snapshot} />
                    </div>
                    {lead.phone && (
                      <span className="dados text-legenda text-tinta-media mt-1.5 block">
                        {lead.phone.replace(/^\+55/, "")}
                      </span>
                    )}
                    <span className="text-legenda text-tinta-fraca mt-1 block">
                      {lead.last_contacted_at
                        ? `contato ${data(lead.last_contacted_at)}`
                        : "sem contato"}
                    </span>
                  </Link>
                ))
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function data(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}
