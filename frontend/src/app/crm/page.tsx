"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Botao, Cabecalho, Casca, Erro, Vazio } from "@/components/casca";
import { Score } from "@/components/lacunas";
import { errorMessage } from "@/lib/auth";
import { listarFunis, listarLeads } from "@/lib/recursos";
import type { Estagio, Lead } from "@/lib/tipos";

/**
 * A prospecção: o funil e a fila de trabalho.
 *
 * Colunas de kanban seriam o reflexo, mas a fila real de quem vende é uma lista ordenada por
 * prioridade — e um kanban de oito colunas não cabe em tela nenhuma. O funil vira uma régua
 * no topo, e embaixo fica a lista.
 */
export default function Prospeccao() {
  const [estagios, setEstagios] = useState<Estagio[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [filtro, setFiltro] = useState<string>("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listarFunis(), listarLeads(filtro ? { stage: filtro } : {})])
      .then(([f, l]) => {
        setEstagios(f.results[0]?.stages ?? []);
        setLeads(l.results);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar a prospecção.")))
      .finally(() => setCarregando(false));
  }, [filtro]);

  const total = estagios.reduce((soma, e) => soma + e.lead_count, 0);

  return (
    <Casca>
      <Cabecalho
        titulo="Prospecção"
        descricao="Quem está na fila, em que ponto da conversa, e o que fazer a seguir."
      />

      {erro && <Erro mensagem={erro} />}

      {estagios.length > 0 && (
        <Regua
          estagios={estagios}
          total={total}
          selecionado={filtro}
          aoSelecionar={(id) => setFiltro((atual) => (atual === id ? "" : id))}
        />
      )}

      {carregando ? (
        <p className="dados text-tinta-fraca text-sm">carregando…</p>
      ) : leads.length === 0 ? (
        <Vazio
          titulo={filtro ? "Nenhum lead neste estágio." : "Nenhum lead ainda. Comece pelo Radar."}
          acao={
            !filtro && (
              <Link href="/">
                <Botao>Ir para o Radar</Botao>
              </Link>
            )
          }
        />
      ) : (
        <ol className="border-linha bg-papel-alto divide-linha divide-y rounded-lg border">
          {leads.map((lead) => (
            <li key={lead.id}>
              <Link
                href={`/crm/${lead.id}`}
                className="hover:bg-papel/60 flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 transition-colors"
              >
                <div className="w-10 shrink-0 text-right">
                  <Score valor={lead.score_snapshot} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-tinta font-medium">{lead.company_name}</div>
                  <div className="text-tinta-fraca mt-0.5 text-xs">
                    {lead.stage_name}
                    {lead.last_contacted_at
                      ? ` · último contato ${data(lead.last_contacted_at)}`
                      : " · sem contato ainda"}
                  </div>
                </div>
                {/* Score mudou desde a entrada: a empresa mexeu no site, e a oportunidade
                    encolheu ou cresceu. É informação de venda, não ruído. */}
                {lead.current_score !== null && lead.current_score !== lead.score_snapshot && (
                  <span className="dados text-tinta-fraca text-xs">hoje {lead.current_score}</span>
                )}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </Casca>
  );
}

/**
 * A régua do funil: uma barra proporcional, não oito colunas.
 *
 * Cada segmento é um estágio, largura proporcional à quantidade. Clicar filtra. Cabe no
 * celular, que é onde o vendedor abre isto entre uma ligação e outra.
 */
function Regua({
  estagios,
  total,
  selecionado,
  aoSelecionar,
}: {
  estagios: Estagio[];
  total: number;
  selecionado: string;
  aoSelecionar: (id: string) => void;
}) {
  return (
    <div className="mb-8">
      <div className="flex gap-1">
        {estagios.map((e) => {
          const ativo = selecionado === e.id;
          const largura =
            total > 0 ? Math.max(6, (e.lead_count / total) * 100) : 100 / estagios.length;
          return (
            <button
              key={e.id}
              onClick={() => aoSelecionar(e.id)}
              aria-pressed={ativo}
              title={`${e.name}: ${e.lead_count}`}
              style={{ width: `${largura}%` }}
              className={`group min-w-0 rounded px-2 py-2 text-left transition-colors ${
                ativo ? "bg-acao text-papel-alto" : "bg-papel-fundo hover:bg-linha"
              }`}
            >
              <div className="dados text-sm font-semibold">{e.lead_count}</div>
              <div
                className={`truncate text-[10px] ${ativo ? "text-papel-alto/80" : "text-tinta-fraca"}`}
              >
                {e.name}
              </div>
            </button>
          );
        })}
      </div>
      {selecionado && (
        <button
          onClick={() => aoSelecionar(selecionado)}
          className="text-tinta-fraca hover:text-tinta mt-2 text-xs"
        >
          Limpar filtro
        </button>
      )}
    </div>
  );
}

function data(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}
