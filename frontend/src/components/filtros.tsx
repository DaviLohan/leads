"use client";

import { Radar, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";

import { Botao } from "@/components/ui/botao";
import { Campo, Marcador, ParDeCampos, Selecao } from "@/components/ui/campo";
import { listarCategorias, listarEstados, listarMunicipios } from "@/lib/recursos";
import type { FiltrosDeEmpresa } from "@/lib/recursos";
import type { Categoria, Estado, Municipio } from "@/lib/tipos";

/**
 * O painel de filtros da tela Empresas.
 *
 * Duas ações, e elas não se parecem de propósito:
 *
 * - **FILTRAR** procura no que já temos. É instantâneo e não custa nada.
 * - **BUSCAR NOVAS EMPRESAS** sai para fontes externas, demora minutos e consome cota de um
 *   serviço comunitário (ADR-0004). Fica separada por régua, com o custo escrito.
 *
 * Os campos são agrupados por pergunta — onde, o quê, presença digital, contato, prioridade —
 * em vez de empilhados numa coluna só. Todos passam pelos primitivos `Campo`/`Selecao`, que é
 * o que garante a mesma altura, o mesmo rótulo e o mesmo foco em todos.
 */
export function PainelDeFiltros({
  valores,
  aoFiltrar,
  aoDescobrir,
}: {
  valores: FiltrosDeEmpresa;
  aoFiltrar: (filtros: FiltrosDeEmpresa) => void;
  aoDescobrir: () => void;
}) {
  const [form, setForm] = useState<FiltrosDeEmpresa>(valores);
  const [estados, setEstados] = useState<Estado[]>([]);
  const [municipios, setMunicipios] = useState<Municipio[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);

  useEffect(() => setForm(valores), [valores]);

  useEffect(() => {
    listarEstados().then((p) => setEstados(p.results));
    listarCategorias().then((p) => setCategorias(p.results));
  }, []);

  // Município só faz sentido depois do estado: 5.571 numa lista só é inutilizável.
  useEffect(() => {
    if (!form.uf) {
      setMunicipios([]);
      return;
    }
    listarMunicipios({ uf: form.uf }).then((p) => setMunicipios(p.results));
  }, [form.uf]);

  function definir(campo: keyof FiltrosDeEmpresa, valor: string | boolean | undefined) {
    setForm((atual) => ({ ...atual, [campo]: valor === "" ? undefined : valor, page: undefined }));
  }

  const ativos = Object.entries(form).filter(
    ([chave, valor]) => valor !== undefined && valor !== "" && chave !== "page",
  ).length;

  return (
    <form
      onSubmit={(evento) => {
        evento.preventDefault();
        aoFiltrar(form);
      }}
      className="border-linha bg-papel-alto rounded-md border"
      aria-label="Filtros"
    >
      <div className="border-linha flex h-12 items-center justify-between border-b px-4">
        <span className="text-tinta flex items-center gap-2 font-medium">
          <SlidersHorizontal size={14} className="text-tinta-fraca" aria-hidden />
          Filtros
        </span>
        {ativos > 0 && (
          <button
            type="button"
            onClick={() => aoFiltrar({})}
            className="text-apoio text-tinta-fraca hover:text-tinta transition-colors"
          >
            Limpar ({ativos})
          </button>
        )}
      </div>

      <div className="space-y-5 p-4">
        <Grupo titulo="Onde">
          <Selecao
            rotulo="Estado"
            valor={form.uf ?? ""}
            aoMudar={(escolhido) => {
              definir("uf", escolhido);
              definir("city", undefined);
            }}
            vazio="Todos os estados"
            opcoes={estados.map((estado) => ({
              valor: estado.uf,
              rotulo: `${estado.uf} — ${estado.name}`,
            }))}
          />

          <Selecao
            rotulo="Cidade"
            valor={form.city ?? ""}
            aoMudar={(escolhido) => definir("city", escolhido)}
            disabled={!form.uf}
            ajuda={!form.uf ? "Escolha o estado primeiro" : undefined}
            vazio={form.uf ? "Todas as cidades" : "—"}
            opcoes={municipios.map((municipio) => ({
              valor: municipio.id,
              rotulo: municipio.name,
            }))}
          />
        </Grupo>

        <Grupo titulo="O quê">
          <Selecao
            rotulo="Segmento"
            valor={form.category ?? ""}
            aoMudar={(escolhido) => definir("category", escolhido)}
            vazio="Todos os segmentos"
            opcoes={categorias.map((categoria) => ({
              valor: categoria.slug,
              rotulo: categoria.name,
            }))}
          />

          <Campo
            rotulo="Nome"
            type="search"
            value={form.q ?? ""}
            onChange={(e) => definir("q", e.target.value)}
            placeholder="parte do nome"
          />
        </Grupo>

        <Grupo titulo="Presença digital">
          <Selecao
            rotulo="Site"
            valor={form.site ?? ""}
            aoMudar={(escolhido) => definir("site", escolhido)}
            vazio="Qualquer situação"
            opcoes={[
              { valor: "not_found", rotulo: "Não identificado nas fontes" },
              { valor: "broken", rotulo: "Com problemas" },
              { valor: "found", rotulo: "Identificado" },
              { valor: "not_checked", rotulo: "Ainda não verificado" },
            ]}
          />
        </Grupo>

        <Grupo titulo="Contato">
          <div className="space-y-1">
            <Marcador
              rotulo="Tem telefone"
              checked={form.has_phone === true || form.has_phone === "true"}
              onChange={(e) => definir("has_phone", e.target.checked ? true : undefined)}
            />
            <Marcador
              rotulo="Tem WhatsApp confirmado"
              checked={form.has_whatsapp === true || form.has_whatsapp === "true"}
              onChange={(e) => definir("has_whatsapp", e.target.checked ? true : undefined)}
            />
            <Marcador
              rotulo="Tem e-mail comercial"
              checked={form.has_email === true || form.has_email === "true"}
              onChange={(e) => definir("has_email", e.target.checked ? true : undefined)}
            />
          </div>
        </Grupo>

        <Grupo titulo="Prioridade">
          {/* Par de campos relacionados: mesma largura e mesma linha de base, por estrutura. */}
          <ParDeCampos>
            <Campo
              rotulo="Score mínimo"
              type="number"
              min={0}
              max={100}
              value={form.score_min ?? ""}
              onChange={(e) => definir("score_min", e.target.value)}
              placeholder="0"
            />
            <Campo
              rotulo="Score máximo"
              type="number"
              min={0}
              max={100}
              value={form.score_max ?? ""}
              onChange={(e) => definir("score_max", e.target.value)}
              placeholder="100"
            />
          </ParDeCampos>

          <Selecao
            rotulo="Prospecção"
            valor={String(form.in_crm ?? "")}
            aoMudar={(escolhido) => definir("in_crm", escolhido)}
            vazio="Todas"
            opcoes={[
              { valor: "false", rotulo: "Ainda não abordadas" },
              { valor: "true", rotulo: "Já no meu funil" },
            ]}
          />

          <Selecao
            rotulo="Ordenar por"
            valor={form.ordering ?? ""}
            aoMudar={(escolhido) => definir("ordering", escolhido)}
            vazio="Maior oportunidade"
            opcoes={[
              { valor: "name", rotulo: "Nome" },
              { valor: "-discovered_at", rotulo: "Descobertas recentes" },
            ]}
          />
        </Grupo>

        <Botao type="submit" variante="primaria" className="w-full">
          Filtrar
        </Botao>
      </div>

      {/* A segunda ação nunca se parece com a primeira: ela sai para a rede e custa cota. */}
      <div className="border-linha bg-papel/40 space-y-2 border-t p-4">
        <p className="text-legenda text-tinta-fraca leading-relaxed">
          Não encontrou? Descobrir novas empresas consulta fontes externas e leva alguns minutos.
        </p>
        <Botao
          type="button"
          variante="secundaria"
          Icone={Radar}
          onClick={aoDescobrir}
          className="w-full"
        >
          Buscar novas empresas
        </Botao>
      </div>
    </form>
  );
}

/** Grupo de campos com rótulo de seção — o que transforma 10 campos empilhados em 5 perguntas. */
function Grupo({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <fieldset className="space-y-3">
      <legend className="rotulo-secao mb-2">{titulo}</legend>
      {children}
    </fieldset>
  );
}
