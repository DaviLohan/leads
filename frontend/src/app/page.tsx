"use client";

import { ArrowRight, PhoneOff, Radar, Search, Trophy, UserPlus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { TabelaDeEmpresas } from "@/components/tabela";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina, CartaoDeMetrica } from "@/components/ui/cabecalho";
import { Erro, Esqueleto, EsqueletoDeTabela, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import { resumoDoCrm } from "@/lib/recursos";
import type { Resumo } from "@/lib/tipos";

/**
 * O Painel: como está a minha prospecção.
 *
 * Não é painel técnico e não tem gráfico decorativo. Responde três perguntas, na ordem em que
 * alguém abre o sistema de manhã: **quantos esperam ligação**, **o que aconteceu hoje** e
 * **quem eu devo abordar agora**.
 *
 * O número em âmbar é **sem contato** — a fila esquecida. Todo painel de vendas destaca o que
 * já foi feito; o que muda o dia é o que ainda não foi.
 */
export default function Painel() {
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    return resumoDoCrm()
      .then(setResumo)
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar o painel.")))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  return (
    <Casca>
      <CabecalhoDaPagina
        titulo="Painel"
        descricao="Onde está a prospecção hoje — e quem abordar em seguida."
        acao={
          <Link href="/empresas">
            <Botao variante="primaria" Icone={Search}>
              Buscar leads
            </Botao>
          </Link>
        }
      />

      {erro && <Erro mensagem={erro} aoTentarNovamente={carregar} className="mb-6" />}

      {carregando ? (
        <div className="space-y-8">
          <div className="border-linha bg-linha grid gap-px overflow-hidden rounded-md border sm:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-papel-alto space-y-2 px-4 py-3.5">
                <Esqueleto className="h-2.5 w-16" />
                <Esqueleto className="h-6 w-10" />
              </div>
            ))}
          </div>
          <EsqueletoDeTabela linhas={5} colunas={5} />
        </div>
      ) : !resumo ? null : (
        <div className="space-y-8">
          {/* Uma faixa só, dividida por linha de 1px: seis cartões soltos com sombra viram
              seis caixas competindo. Aqui eles leem como uma régua de números. */}
          <section
            aria-label="Resumo da prospecção"
            className="border-linha bg-linha grid gap-px overflow-hidden rounded-md border sm:grid-cols-3 lg:grid-cols-6"
          >
            <CartaoDeMetrica rotulo="No funil" valor={resumo.total} Icone={Radar} />
            <CartaoDeMetrica
              rotulo="Sem contato"
              valor={resumo.sem_contato}
              contexto="esperando ligação"
              destaque
              Icone={PhoneOff}
            />
            <CartaoDeMetrica rotulo="Novos hoje" valor={resumo.novos_hoje} Icone={UserPlus} />
            <CartaoDeMetrica rotulo="Contatados hoje" valor={resumo.contatados_hoje} />
            <CartaoDeMetrica rotulo="Ganhos" valor={resumo.ganhos} Icone={Trophy} />
            <CartaoDeMetrica
              rotulo="Conversão"
              valor={resumo.conversao === null ? "—" : `${Math.round(resumo.conversao * 100)}%`}
              contexto={
                resumo.conversao === null ? "nada encerrado ainda" : "sobre leads encerrados"
              }
            />
          </section>

          {resumo.total > 0 && (
            <section>
              <TituloDeSecao titulo="Funil" href="/leads?vista=funil" rotulo="ver funil" />
              <div className="border-linha bg-papel-alto flex gap-1 rounded-md border p-3">
                {resumo.por_estagio.map((estagio) => {
                  const largura =
                    resumo.total > 0
                      ? Math.max(6, (estagio.lead_count / resumo.total) * 100)
                      : 100 / resumo.por_estagio.length;
                  return (
                    <div
                      key={estagio.code}
                      style={{ width: `${largura}%` }}
                      title={`${estagio.name}: ${estagio.lead_count}`}
                      className={`min-w-0 rounded-sm px-2.5 py-2 ${
                        estagio.is_won ? "bg-ganho-fraca" : "bg-papel-fundo"
                      }`}
                    >
                      <div className="dados text-tinta font-semibold">{estagio.lead_count}</div>
                      <div className="text-legenda text-tinta-fraca truncate">{estagio.name}</div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section>
            <TituloDeSecao
              titulo="Melhores oportunidades"
              href="/empresas?in_crm=false"
              rotulo="ver todas"
            />
            {resumo.melhores_oportunidades.length === 0 ? (
              <Vazio
                titulo="Nenhuma empresa fora do funil ainda."
                descricao="Descubra empresas nas fontes externas para começar a prospectar."
                Icone={Radar}
                acao={
                  <Link href="/buscas">
                    <Botao variante="primaria">Buscar novas empresas</Botao>
                  </Link>
                }
              />
            ) : (
              <TabelaDeEmpresas empresas={resumo.melhores_oportunidades} />
            )}
          </section>
        </div>
      )}
    </Casca>
  );
}

function TituloDeSecao({ titulo, href, rotulo }: { titulo: string; href: string; rotulo: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between">
      <h2 className="rotulo-secao">{titulo}</h2>
      <Link
        href={href}
        className="text-apoio text-acao inline-flex items-center gap-1 font-medium hover:underline"
      >
        {rotulo}
        <ArrowRight size={13} aria-hidden />
      </Link>
    </div>
  );
}
