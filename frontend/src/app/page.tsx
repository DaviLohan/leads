"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Botao, Cabecalho, Casca, Erro, Vazio } from "@/components/casca";
import { BarraDeLacunas, Score } from "@/components/lacunas";
import { errorMessage } from "@/lib/auth";
import { criarLead, lacunasDe, listarAnalises, listarPontuacoes } from "@/lib/recursos";
import type { Analise, Pontuacao } from "@/lib/tipos";

/**
 * O Radar: a folha de ligações.
 *
 * A tela abre com a frase que é a tese do produto — quantas empresas não têm site — porque
 * é isso que o vendedor precisa saber antes de qualquer gráfico. Depois vem a lista, na
 * ordem em que se trabalha: maior lacuna primeiro.
 */
export default function Radar() {
  const [pontuacoes, setPontuacoes] = useState<Pontuacao[]>([]);
  const [analises, setAnalises] = useState<Map<string, Analise>>(new Map());
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listarPontuacoes(), listarAnalises()])
      .then(([p, a]) => {
        setPontuacoes(p.results);
        // A análise mais recente por empresa; a listagem já vem da mais nova para a mais velha.
        const mapa = new Map<string, Analise>();
        for (const analise of a.results) {
          if (!mapa.has(analise.company)) mapa.set(analise.company, analise);
        }
        setAnalises(mapa);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar o radar.")))
      .finally(() => setCarregando(false));
  }, []);

  const semSite = pontuacoes.filter((p) =>
    p.components.some((c) => c.rule_code === "sem_site" || c.rule_code === "site_fora_do_ar"),
  ).length;

  return (
    <Casca>
      <Cabecalho
        titulo="Radar"
        descricao="Quem tem menos presença digital aparece primeiro. É onde há mais para vender."
      />

      {erro && <Erro mensagem={erro} />}

      {!carregando && pontuacoes.length > 0 && <Tese total={pontuacoes.length} semSite={semSite} />}

      {carregando ? (
        <p className="dados text-tinta-fraca text-sm">carregando…</p>
      ) : pontuacoes.length === 0 ? (
        <Vazio
          titulo="Nenhuma empresa analisada ainda."
          acao={
            <Link href="/buscas">
              <Botao>Criar a primeira busca</Botao>
            </Link>
          }
        />
      ) : (
        <ol className="border-linha bg-papel-alto divide-linha divide-y rounded-lg border">
          {pontuacoes.map((p) => (
            <Linha key={p.id} pontuacao={p} analise={analises.get(p.company)} />
          ))}
        </ol>
      )}
    </Casca>
  );
}

/**
 * A tese, em números reais.
 *
 * Não é um cartão de KPI: é uma frase. O número grande é a ausência, porque a ausência é o
 * produto — e ler "8 de 9 não têm site" diz mais que qualquer gráfico de rosca.
 */
function Tese({ total, semSite }: { total: number; semSite: number }) {
  if (semSite === 0) return null;
  return (
    <p className="font-display text-tinta mb-8 max-w-2xl text-2xl leading-tight font-bold tracking-tight">
      <span className="dados text-lacuna text-5xl font-semibold">{semSite}</span>{" "}
      <span className="text-tinta-fraca font-medium">de {total} empresas analisadas</span> não têm
      site oficial identificado.
    </p>
  );
}

function Linha({ pontuacao, analise }: { pontuacao: Pontuacao; analise?: Analise }) {
  const [criando, setCriando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [virouLead, setVirouLead] = useState(false);

  const temSite = Boolean(analise);
  const lacunas = lacunasDe(analise, temSite);

  async function prospectar() {
    setCriando(true);
    setAviso(null);
    try {
      await criarLead(pontuacao.company);
      setVirouLead(true);
    } catch (e) {
      setAviso(errorMessage(e, "Não foi possível criar o lead."));
    } finally {
      setCriando(false);
    }
  }

  return (
    <li className="hover:bg-papel/60 flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-4 transition-colors">
      <div className="w-12 shrink-0 text-right">
        <Score valor={pontuacao.value} />
      </div>

      <div className="min-w-0 flex-1">
        <Link
          href={`/empresas/${pontuacao.company}`}
          className="text-tinta hover:text-acao font-medium"
        >
          {pontuacao.company_name}
        </Link>
        <div className="mt-2">
          <BarraDeLacunas lacunas={lacunas} rotulos />
        </div>
      </div>

      <div className="min-w-0 flex-1 basis-full sm:basis-auto">
        <ul className="text-tinta-fraca space-y-0.5 text-xs">
          {pontuacao.components.slice(0, 2).map((c) => (
            <li key={c.rule_code} className="flex gap-2">
              <span
                className={`dados w-8 shrink-0 text-right ${c.points > 0 ? "text-lacuna" : ""}`}
              >
                {c.points > 0 ? `+${c.points}` : c.points}
              </span>
              <span className="truncate">{c.reason}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="shrink-0">
        {virouLead ? (
          <Link href="/crm" className="text-acao text-sm font-medium">
            No funil →
          </Link>
        ) : (
          <Botao variante="quieta" onClick={prospectar} disabled={criando}>
            {criando ? "…" : "Prospectar"}
          </Botao>
        )}
        {aviso && <p className="text-perdido mt-1 max-w-[16rem] text-xs">{aviso}</p>}
      </div>
    </li>
  );
}
