"use client";

import { Radar } from "lucide-react";

import { useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { Botao } from "@/components/ui/botao";
import { Selecao, SelecaoMultipla } from "@/components/ui/campo";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Etiqueta } from "@/components/ui/etiqueta";
import { Erro, EsqueletoDeTabela, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import {
  cancelarBusca,
  criarBusca,
  jobsDaBusca,
  listarBuscas,
  listarCategorias,
  listarEstados,
  listarMunicipios,
  prever,
  type Criterios,
  type Previsao,
} from "@/lib/recursos";
import type { Busca, Categoria, Estado, JobDeBusca } from "@/lib/tipos";

const SITUACAO: Record<
  Busca["status"],
  { rotulo: string; tom: "neutro" | "lacuna" | "ganho" | "perdido" }
> = {
  PENDING: { rotulo: "Aguardando", tom: "neutro" },
  RUNNING: { rotulo: "Em andamento", tom: "lacuna" },
  COMPLETED: { rotulo: "Concluída", tom: "ganho" },
  PARTIALLY_COMPLETED: { rotulo: "Concluída com falhas", tom: "lacuna" },
  FAILED: { rotulo: "Falhou", tom: "perdido" },
  CANCELLED: { rotulo: "Cancelada", tom: "neutro" },
};

export default function Buscas() {
  const [buscas, setBuscas] = useState<Busca[]>([]);
  const [estados, setEstados] = useState<Estado[]>([]);
  // O catálogo vem do banco. Fixá-lo aqui mandava slug onde a API espera UUID, e categoria
  // nova nunca apareceria na tela.
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  const recarregar = () =>
    listarBuscas()
      .then((p) => setBuscas(p.results))
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar as buscas.")));

  useEffect(() => {
    Promise.all([
      recarregar(),
      listarEstados().then((p) => setEstados(p.results)),
      listarCategorias().then((p) => setCategorias(p.results)),
    ]).finally(() => setCarregando(false));
  }, []);

  // Enquanto houver busca rodando, atualiza sozinho. Sem isso, a pessoa fica apertando F5
  // durante os minutos em que a varredura acontece.
  useEffect(() => {
    const rodando = buscas.some((b) => b.status === "RUNNING" || b.status === "PENDING");
    if (!rodando) return;
    const timer = setInterval(recarregar, 4000);
    return () => clearInterval(timer);
  }, [buscas]);

  return (
    <Casca>
      <CabecalhoDaPagina
        titulo="Buscas"
        descricao="Escolha onde e o quê procurar. A varredura roda em segundo plano."
      />

      {erro && <Erro mensagem={erro} />}

      <NovaBusca estados={estados} categorias={categorias} aoCriar={recarregar} />

      <h2 className="rotulo-secao mt-10 mb-3">Histórico</h2>

      {carregando ? (
        <EsqueletoDeTabela linhas={3} colunas={4} />
      ) : buscas.length === 0 ? (
        <Vazio
          titulo="Nenhuma busca ainda."
          descricao="Escolha estado, segmento e fonte no formulário acima para descobrir empresas novas."
          Icone={Radar}
        />
      ) : (
        <ul className="space-y-3">
          {buscas.map((b) => (
            <ItemDeBusca key={b.id} busca={b} aoMudar={recarregar} />
          ))}
        </ul>
      )}
    </Casca>
  );
}

function NovaBusca({
  estados,
  categorias,
  aoCriar,
}: {
  estados: Estado[];
  categorias: Categoria[];
  aoCriar: () => void;
}) {
  const [uf, setUf] = useState("");
  const [municipios, setMunicipios] = useState<string[]>([]);
  const [nomesDeMunicipio, setNomesDeMunicipio] = useState<Record<string, string>>({});
  const [categoria, setCategoria] = useState<string>("");
  const [previsao, setPrevisao] = useState<Previsao | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // `resolve_cities` **soma** `uf` e `city_ids`. Mandar os dois devolveria o estado inteiro, e
  // o recorte não recortaria nada — em silêncio, que é o pior jeito de falhar. Ou um, ou outro.
  const criterios = (): Criterios => ({
    ...(municipios.length ? { city_ids: municipios } : { uf: [uf] }),
    category_ids: [categoria],
    provider_slugs: ["osm-overpass"],
  });

  // O catálogo chega depois da primeira renderização; a primeira categoria vira o padrão.
  useEffect(() => {
    const primeira = categorias[0];
    if (!categoria && primeira) setCategoria(primeira.id);
  }, [categorias, categoria]);

  // A previsão existe para que ninguém peça 399 municípios sem saber. Varrer o Paraná
  // inteiro contra o Overpass público leva horas e é abuso de serviço comunitário.
  useEffect(() => {
    if (!uf || !categoria) {
      setPrevisao(null);
      return;
    }
    let valido = true;
    prever(criterios())
      .then((r) => valido && setPrevisao(r))
      .catch(() => valido && setPrevisao(null));
    return () => {
      valido = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uf, categoria, municipios]);

  // Trocar de estado larga os municípios: senão fica cidade de outro estado presa no critério,
  // e a busca sai de um lugar que a tela não está mais mostrando.
  function trocarEstado(novo: string) {
    setUf(novo);
    setMunicipios([]);
  }

  async function procurarMunicipio(termo: string) {
    if (!uf) return [];
    // Busca no servidor porque a lista não cabe numa página: são 5.571 municípios e a API
    // pagina em 200 — em MG (853) e SP (645) filtrar no cliente esconderia a maioria.
    const pagina = await listarMunicipios({ uf, q: termo });
    setNomesDeMunicipio((atual) => ({
      ...atual,
      ...Object.fromEntries(pagina.results.map((m) => [m.id, m.name])),
    }));
    return pagina.results.map((m) => ({ valor: m.id, rotulo: m.name }));
  }

  const nomeDaCategoria = categorias.find((c) => c.id === categoria)?.name ?? "";
  const acimaDoLimite = previsao !== null && previsao.estimated_jobs > previsao.max_jobs;

  return (
    <form
      onSubmit={async (evento) => {
        evento.preventDefault();
        setErro(null);
        setEnviando(true);
        try {
          const onde = municipios.length
            ? municipios.map((id) => nomesDeMunicipio[id] ?? id).join(", ")
            : uf;
          await criarBusca(`${nomeDaCategoria} em ${onde}`, criterios());
          setMunicipios([]);
          aoCriar();
        } catch (e) {
          setErro(errorMessage(e, "Não foi possível criar a busca."));
        } finally {
          setEnviando(false);
        }
      }}
      className="border-linha bg-papel-alto rounded-md border p-5"
    >
      <div className="flex flex-wrap items-end gap-4">
        <Selecao
          rotulo="Estado"
          className="w-56"
          valor={uf}
          aoMudar={trocarEstado}
          required
          vazio="Escolha…"
          opcoes={estados.map((estado) => ({ valor: estado.uf, rotulo: estado.name }))}
        />

        <SelecaoMultipla
          rotulo="Municípios"
          className="min-w-72 flex-1"
          valores={municipios}
          aoMudar={setMunicipios}
          aoBuscar={procurarMunicipio}
          rotulosConhecidos={nomesDeMunicipio}
          opcoes={[]}
          disabled={!uf}
          espaco={uf ? "Digite para procurar" : "Escolha o estado primeiro"}
          ajuda="Vazio = estado inteiro"
        />

        <Selecao
          rotulo="Ramo"
          className="w-64"
          valor={categoria}
          aoMudar={setCategoria}
          required
          opcoes={categorias.map((c) => ({ valor: c.id, rotulo: c.name }))}
        />

        <Botao type="submit" disabled={enviando || !uf || !categoria || acimaDoLimite}>
          {enviando ? "Criando…" : "Criar busca"}
        </Botao>
      </div>

      {/* Uma mensagem só. Antes o aviso âmbar e o erro vermelho diziam a mesma coisa — e o
          vermelho só aparecia depois de clicar, para dizer o que a tela já sabia. */}
      {previsao !== null && <Alcance previsao={previsao} />}
      {erro && <Erro mensagem={erro} className="mt-3" />}
    </form>
  );
}

/**
 * O alcance da busca, numa frase só, com o tom mudando conforme o caso.
 *
 * Impedimento é vermelho e diz o que fazer; alcance grande é âmbar e avisa do custo; o resto é
 * só a contagem. Antes eram duas mensagens dizendo o mesmo, e a decisiva só chegava depois de
 * clicar — para informar o que a tela já sabia.
 */
function Alcance({ previsao }: { previsao: Previsao }) {
  const { estimated_jobs: varreduras, max_jobs: limite } = previsao;

  if (varreduras > limite) {
    return (
      <p className="text-perdido text-apoio mt-4">
        Isso daria <span className="dados font-semibold">{varreduras}</span> varreduras, e o limite
        é <span className="dados font-semibold">{limite}</span> por busca. Escolha alguns municípios
        acima.
      </p>
    );
  }

  return (
    <p className="text-tinta-fraca text-apoio mt-4">
      Vai varrer <span className="dados text-tinta font-semibold">{varreduras}</span>{" "}
      {varreduras === 1 ? "município" : "municípios"}.
      {varreduras > 100 && <span className="text-lacuna"> Isso leva horas.</span>}
    </p>
  );
}

function ItemDeBusca({ busca, aoMudar }: { busca: Busca; aoMudar: () => void }) {
  const [aberta, setAberta] = useState(false);
  const [jobs, setJobs] = useState<JobDeBusca[]>([]);
  const situacao = SITUACAO[busca.status];

  useEffect(() => {
    if (!aberta) return;
    jobsDaBusca(busca.id)
      .then((p) => setJobs(p.results))
      .catch(() => setJobs([]));
  }, [aberta, busca.id, busca.progress]);

  return (
    <li className="border-linha bg-papel-alto rounded-md border">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <button
          onClick={() => setAberta((a) => !a)}
          className="text-tinta hover:text-acao text-left font-medium"
          aria-expanded={aberta}
        >
          {busca.name}
        </button>
        <Etiqueta tom={situacao.tom}>{situacao.rotulo}</Etiqueta>

        <div className="ml-auto flex items-center gap-3">
          <div className="bg-papel-fundo h-1.5 w-28 overflow-hidden rounded-full">
            <div
              className="bg-acao h-full transition-[width] duration-500"
              style={{ width: `${busca.progress}%` }}
            />
          </div>
          <span className="dados text-tinta-fraca text-legenda w-10 text-right">
            {busca.progress}%
          </span>
          {/* O que a busca rendeu, não só se terminou: achadas, novas, já conhecidas. */}
          {busca.found_count > 0 && (
            <span className="dados text-tinta-fraca text-legenda whitespace-nowrap">
              {busca.found_count} achadas ·{" "}
              <span className="text-lacuna">{busca.new_count} novas</span>
              {busca.duplicate_count > 0 && ` · ${busca.duplicate_count} já conhecidas`}
              {busca.error_count > 0 && (
                <span className="text-perdido"> · {busca.error_count} com erro</span>
              )}
            </span>
          )}
          {!["COMPLETED", "CANCELLED", "FAILED"].includes(busca.status) && (
            <Botao
              variante="secundaria"
              onClick={async () => {
                await cancelarBusca(busca.id);
                aoMudar();
              }}
            >
              Cancelar
            </Botao>
          )}
        </div>
      </div>

      {aberta && (
        <div className="border-linha border-t px-4 py-3">
          {jobs.length === 0 ? (
            <p className="text-tinta-fraca text-apoio">Sem municípios ainda.</p>
          ) : (
            <table className="text-apoio w-full">
              <thead>
                <tr className="text-tinta-fraca text-legenda text-left">
                  <th className="pb-2 font-medium">Município</th>
                  <th className="pb-2 font-medium">Situação</th>
                  <th className="pb-2 text-right font-medium">Achadas</th>
                  <th className="pb-2 text-right font-medium">Novas</th>
                </tr>
              </thead>
              <tbody className="divide-linha divide-y">
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td className="py-1.5">
                      {j.city}
                      <span className="text-tinta-fraca">/{j.uf}</span>
                    </td>
                    <td className="text-tinta-fraca text-legenda py-1.5">
                      {j.last_error ? (
                        <span className="text-perdido" title={j.last_error}>
                          falhou
                        </span>
                      ) : (
                        j.status.toLowerCase()
                      )}
                    </td>
                    <td className="dados py-1.5 text-right">{j.found_count}</td>
                    <td className="dados text-lacuna py-1.5 text-right">{j.new_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </li>
  );
}
