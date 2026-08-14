"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Botao, Cabecalho, Casca, Erro, Etiqueta, Vazio } from "@/components/casca";
import { BarraDeLacunas, Score } from "@/components/lacunas";
import { errorMessage } from "@/lib/auth";
import {
  criarLead,
  lacunasDe,
  listarAnalises,
  listarOportunidades,
  pontuacaoDaEmpresa,
  reanalisar,
} from "@/lib/recursos";
import type { Analise, Oportunidade, Pontuacao } from "@/lib/tipos";

/**
 * O detalhe da empresa: o diagnóstico completo, com evidência.
 *
 * A ordem da página é a ordem de uma conversa de venda: quanto vale (score), o que falta
 * (lacunas), o que dá para vender (oportunidades), e por que se afirma isso (achados).
 */
export default function DetalheDaEmpresa() {
  const { id } = useParams<{ id: string }>();
  const [pontuacao, setPontuacao] = useState<Pontuacao | null>(null);
  const [analise, setAnalise] = useState<Analise | null>(null);
  const [oportunidades, setOportunidades] = useState<Oportunidade[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      pontuacaoDaEmpresa(id),
      listarAnalises({ company: id }),
      listarOportunidades({ company: id, status: "OPEN" }),
    ])
      .then(([p, a, o]) => {
        setPontuacao(p.results[0] ?? null);
        setAnalise(a.results[0] ?? null);
        setOportunidades(o.results);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar a empresa.")))
      .finally(() => setCarregando(false));
  }, [id]);

  if (carregando) {
    return (
      <Casca>
        <p className="dados text-tinta-fraca text-sm">carregando…</p>
      </Casca>
    );
  }

  const nome = pontuacao?.company_name ?? analise?.company_name ?? "Empresa";
  const lacunas = lacunasDe(analise ?? undefined, Boolean(analise));

  return (
    <Casca>
      <Link href="/" className="text-tinta-fraca hover:text-tinta mb-4 inline-block text-sm">
        ← Radar
      </Link>

      <Cabecalho
        titulo={nome}
        acao={
          <div className="flex gap-2">
            <Botao
              variante="quieta"
              onClick={async () => {
                setAviso(null);
                try {
                  await reanalisar(id);
                  setAviso("Análise enfileirada. Atualize em alguns segundos.");
                } catch (e) {
                  setAviso(errorMessage(e, "Não foi possível reanalisar."));
                }
              }}
            >
              Reanalisar site
            </Botao>
            <Botao
              onClick={async () => {
                setAviso(null);
                try {
                  await criarLead(id);
                  setAviso("Lead criado. Está na Prospecção.");
                } catch (e) {
                  setAviso(errorMessage(e, "Não foi possível criar o lead."));
                }
              }}
            >
              Prospectar
            </Botao>
          </div>
        }
      />

      {erro && <Erro mensagem={erro} />}
      {aviso && <p className="text-acao mb-6 text-sm">{aviso}</p>}

      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-8">
          <Bloco titulo="O que falta">
            <BarraDeLacunas lacunas={lacunas} rotulos />
            {!analise && (
              <p className="text-tinta-fraca mt-3 text-sm">
                O site desta empresa ainda não foi verificado.
              </p>
            )}
          </Bloco>

          <Bloco titulo="Oportunidades">
            {oportunidades.length === 0 ? (
              <Vazio titulo="Nenhuma oportunidade aberta." />
            ) : (
              <ul className="space-y-3">
                {oportunidades.map((o) => (
                  <li key={o.id} className="border-linha border-l-2 pl-3">
                    <div className="text-tinta font-medium">{o.type_name}</div>
                    <p className="text-tinta-fraca mt-0.5 text-sm">{o.type_description}</p>
                  </li>
                ))}
              </ul>
            )}
          </Bloco>

          <Bloco titulo="O que a análise viu">
            {!analise ? (
              <Vazio titulo="Site ainda não verificado." />
            ) : analise.status !== "OK" ? (
              <div className="space-y-2">
                <Etiqueta tom="perdido">{rotuloDaAnalise(analise.status)}</Etiqueta>
                <p className="text-tinta-fraca text-sm">{analise.error_detail}</p>
              </div>
            ) : (
              <>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                  <Dado rotulo="Endereço" valor={analise.final_url} />
                  <Dado rotulo="HTTP" valor={String(analise.http_status)} />
                  <Dado rotulo="Resposta" valor={`${analise.response_time_ms} ms`} />
                </dl>
                {analise.findings.length > 0 && (
                  <ul className="mt-4 space-y-2">
                    {analise.findings.map((f) => (
                      <li key={f.id} className="flex gap-3 text-sm">
                        <span className="w-16 shrink-0">
                          <Etiqueta tom={f.severity === "HIGH" ? "lacuna" : "neutro"}>
                            {f.severity === "HIGH" ? "alta" : f.severity.toLowerCase()}
                          </Etiqueta>
                        </span>
                        <span className="text-tinta-fraca">{f.detail || f.code_label}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Bloco>
        </div>

        <aside className="space-y-6">
          <div className="border-linha bg-papel-alto rounded-lg border p-5">
            <div className="flex items-baseline gap-3">
              <Score valor={pontuacao?.value ?? null} tamanho="lg" />
              <span className="text-tinta-fraca text-xs">de 100</span>
            </div>
            <p className="text-tinta-fraca mt-1 text-xs">Prioridade de abordagem</p>

            {pontuacao && pontuacao.components.length > 0 && (
              <ul className="border-linha mt-5 space-y-2 border-t pt-4">
                {pontuacao.components.map((c) => (
                  <li key={c.rule_code} className="flex gap-3 text-sm">
                    <span
                      className={`dados w-8 shrink-0 text-right font-semibold ${
                        c.points > 0 ? "text-lacuna" : "text-tinta-fraca"
                      }`}
                    >
                      {c.points > 0 ? `+${c.points}` : c.points}
                    </span>
                    <span className="text-tinta-fraca">{c.reason}</span>
                  </li>
                ))}
              </ul>
            )}
            {pontuacao && (
              <p className="text-tinta-fraca/70 dados mt-4 text-[11px]">
                regras {pontuacao.version}
              </p>
            )}
          </div>
        </aside>
      </div>
    </Casca>
  );
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-tinta-fraca mb-3 text-xs font-semibold tracking-[0.1em] uppercase">
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function Dado({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-tinta-fraca text-xs">{rotulo}</dt>
      <dd className="dados text-tinta truncate text-sm">{valor}</dd>
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
