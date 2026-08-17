"use client";

import { Building2, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Casca } from "@/components/casca";
import { PainelDeFiltros } from "@/components/filtros";
import { BarraDeLote } from "@/components/lote";
import { TabelaDeEmpresas } from "@/components/tabela";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Erro, EsqueletoDeTabela, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import { listarEmpresas, type FiltrosDeEmpresa } from "@/lib/recursos";
import type { Empresa } from "@/lib/tipos";

/**
 * Empresas — a tela onde o trabalho começa.
 *
 * É a resposta à pergunta que o produto existe para responder: *quem, aqui perto, tem lacuna
 * digital e telefone para eu ligar agora?* Filtro à esquerda, tabela à direita, telefone na
 * própria linha.
 *
 * Os filtros vivem na URL. Isso não é detalhe técnico: é o que permite recarregar sem perder
 * o recorte, voltar pelo botão do navegador e mandar "olha esta lista" para o colega.
 */
export default function Empresas() {
  return (
    <Casca>
      {/* `useSearchParams` exige fronteira de Suspense no App Router. */}
      <Suspense fallback={<EsqueletoDeTabela />}>
        <Conteudo />
      </Suspense>
    </Casca>
  );
}

function Conteudo() {
  const router = useRouter();
  const parametros = useSearchParams();
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [total, setTotal] = useState(0);
  const [temProxima, setTemProxima] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionadas, setSelecionadas] = useState<Set<string>>(new Set());

  // A URL é a fonte da verdade do filtro; o estado do formulário é só rascunho.
  const filtros = useMemo(
    () => Object.fromEntries(parametros.entries()) as FiltrosDeEmpresa,
    [parametros],
  );
  const pagina = Number(filtros.page ?? 1);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    return listarEmpresas(filtros)
      .then((p) => {
        setEmpresas(p.results);
        setTotal(p.count);
        setTemProxima(Boolean(p.next));
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar as empresas.")))
      .finally(() => setCarregando(false));
  }, [filtros]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function aplicar(novos: FiltrosDeEmpresa) {
    const busca = new URLSearchParams();
    for (const [chave, valor] of Object.entries(novos)) {
      if (valor !== undefined && valor !== "" && valor !== false) busca.set(chave, String(valor));
    }
    router.replace(busca.size ? `/empresas?${busca}` : "/empresas");
  }

  const comOportunidade = empresas.filter((e) => e.opportunities.length > 0).length;

  return (
    <>
      <CabecalhoDaPagina
        titulo="Empresas"
        descricao="Filtre a base por onde falta presença digital. O telefone está na própria linha."
        contador={carregando ? undefined : `${total} ${total === 1 ? "empresa" : "empresas"}`}
        acao={
          total > 0 ? (
            <a href={`/api/v1/companies/export/${parametros.size ? `?${parametros}` : ""}`}>
              <Botao variante="secundaria" Icone={Download}>
                Exportar CSV
              </Botao>
            </a>
          ) : undefined
        }
      />

      {/* 17rem de filtro + resto para a tabela. A coluna de filtros acompanha a rolagem: numa
          lista de 200 linhas, voltar ao topo para mudar um filtro é trabalho perdido. */}
      <div className="grid items-start gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-8">
          <PainelDeFiltros
            valores={filtros}
            aoFiltrar={aplicar}
            aoDescobrir={() => router.push("/buscas")}
          />
        </aside>

        <section className="min-w-0 space-y-4">
          {erro && <Erro mensagem={erro} aoTentarNovamente={carregar} />}

          {carregando ? (
            <EsqueletoDeTabela linhas={8} colunas={6} />
          ) : empresas.length === 0 ? (
            <Vazio
              titulo="Nenhuma empresa com esses filtros."
              descricao="Tente afrouxar o recorte, ou descubra empresas novas nas fontes externas."
              Icone={Building2}
              acao={
                <Botao variante="secundaria" onClick={() => aplicar({})}>
                  Limpar filtros
                </Botao>
              }
            />
          ) : (
            <>
              <BarraDeLote
                selecionadas={[...selecionadas]}
                aoConcluir={() => {
                  setSelecionadas(new Set());
                  carregar();
                }}
              />

              {comOportunidade > 0 && (
                <p className="text-legenda text-tinta-fraca">
                  <span className="dados text-lacuna">{comOportunidade}</span> das {empresas.length}{" "}
                  nesta página têm oportunidade aberta
                </p>
              )}

              <TabelaDeEmpresas
                empresas={empresas}
                selecao={{
                  selecionadas,
                  aoAlternar: (id) =>
                    setSelecionadas((atual) => {
                      const proximo = new Set(atual);
                      if (!proximo.delete(id)) proximo.add(id);
                      return proximo;
                    }),
                  aoAlternarPagina: (marcar) =>
                    setSelecionadas((atual) => {
                      const proximo = new Set(atual);
                      for (const empresa of empresas) {
                        if (marcar) proximo.add(empresa.id);
                        else proximo.delete(empresa.id);
                      }
                      return proximo;
                    }),
                }}
              />

              <Paginacao
                pagina={pagina}
                total={total}
                mostrando={empresas.length}
                temProxima={temProxima}
                aoIr={(destino) => aplicar({ ...filtros, page: destino })}
              />
            </>
          )}
        </section>
      </div>
    </>
  );
}

/** Paginação com contexto: "1–25 de 347" responde onde estou; o número da página sozinho não. */
function Paginacao({
  pagina,
  total,
  mostrando,
  temProxima,
  aoIr,
}: {
  pagina: number;
  total: number;
  mostrando: number;
  temProxima: boolean;
  aoIr: (pagina: number) => void;
}) {
  if (pagina === 1 && !temProxima) return null;
  const inicio = (pagina - 1) * 25 + 1;

  return (
    <div className="flex items-center justify-between gap-3">
      <p className="text-apoio text-tinta-fraca">
        <span className="dados">
          {inicio}–{inicio + mostrando - 1}
        </span>{" "}
        de <span className="dados">{total}</span>
      </p>
      <div className="flex items-center gap-2">
        <Botao
          variante="secundaria"
          Icone={ChevronLeft}
          disabled={pagina <= 1}
          onClick={() => aoIr(pagina - 1)}
        >
          Anterior
        </Botao>
        <Botao variante="secundaria" disabled={!temProxima} onClick={() => aoIr(pagina + 1)}>
          Próxima
          <ChevronRight size={16} aria-hidden />
        </Botao>
      </div>
    </div>
  );
}
