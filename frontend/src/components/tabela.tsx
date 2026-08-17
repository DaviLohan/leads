"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { Ausente, BotaoWhatsApp, Telefone } from "@/components/telefone";
import { Etiqueta, EtiquetaDeEstagio, Score } from "@/components/ui/etiqueta";
import type { Empresa } from "@/lib/tipos";

/**
 * A tabela de empresas — a superfície central do produto.
 *
 * Hierarquia fixa, e é o que permite ler trinta linhas em segundos: **quem é** (nome, com a
 * oportunidade logo abaixo), **onde está**, **como falar** (telefone e WhatsApp), **quanto
 * vale** (score) e **em que pé está** (situação).
 *
 * Ofício de tabela que a versão anterior não tinha:
 * - cabeçalho fixo ao rolar, para não se perder a coluna na linha 40;
 * - altura de linha constante (56px), que é o que faz a coluna de números formar régua;
 * - linha selecionada com fundo próprio, e não só a caixa marcada;
 * - ações que aparecem no hover, sem ocupar peso visual permanente;
 * - larguras declaradas em `<colgroup>`, para a tabela não dançar quando um nome é longo.
 */

const COLUNAS = [
  { chave: "empresa", rotulo: "Empresa", largura: "auto" },
  { chave: "segmento", rotulo: "Segmento", largura: "10rem" },
  { chave: "local", rotulo: "Localização", largura: "10rem" },
  { chave: "telefone", rotulo: "Telefone", largura: "11rem" },
  { chave: "whatsapp", rotulo: "WhatsApp", largura: "7rem" },
  { chave: "site", rotulo: "Site", largura: "10rem" },
  { chave: "score", rotulo: "Score", largura: "5.5rem" },
  { chave: "situacao", rotulo: "Situação", largura: "8rem" },
  { chave: "acoes", rotulo: "", largura: "3rem" },
];

export function TabelaDeEmpresas({
  empresas,
  selecao,
}: {
  empresas: Empresa[];
  /** Ausente = tabela sem seleção. A coluna de caixas só existe onde há ação em lote. */
  selecao?: {
    selecionadas: Set<string>;
    aoAlternar: (id: string) => void;
    aoAlternarPagina: (marcar: boolean) => void;
  };
}) {
  const todasMarcadas =
    empresas.length > 0 && empresas.every((e) => selecao?.selecionadas.has(e.id));

  return (
    <div className="border-linha bg-papel-alto overflow-x-auto rounded-md border">
      <table className="text-corpo w-full min-w-[64rem] border-collapse">
        <colgroup>
          {selecao && <col style={{ width: "2.75rem" }} />}
          {COLUNAS.map((c) => (
            <col key={c.chave} style={{ width: c.largura }} />
          ))}
        </colgroup>

        <thead className="bg-papel-alto sticky top-0 z-[var(--z-sticky)]">
          <tr className="border-linha border-b">
            {selecao && (
              <th scope="col" className="px-3">
                <input
                  type="checkbox"
                  checked={todasMarcadas}
                  onChange={(e) => selecao.aoAlternarPagina(e.target.checked)}
                  aria-label="Selecionar a página inteira"
                  className="accent-acao size-4 align-middle"
                />
              </th>
            )}
            {COLUNAS.map((c) => (
              <th
                key={c.chave}
                scope="col"
                className={`text-legenda text-tinta-fraca h-10 px-3 text-left font-semibold tracking-wide uppercase ${
                  c.chave === "score" ? "text-right" : ""
                }`}
              >
                {c.rotulo}
              </th>
            ))}
          </tr>
        </thead>

        <tbody className="divide-linha divide-y">
          {empresas.map((empresa) => {
            const marcada = selecao?.selecionadas.has(empresa.id) ?? false;
            return (
              <tr
                key={empresa.id}
                className={`group h-14 transition-colors ${
                  marcada ? "bg-acao-fraca/60" : "hover:bg-papel/70"
                }`}
              >
                {selecao && (
                  <td className="px-3">
                    <input
                      type="checkbox"
                      checked={marcada}
                      onChange={() => selecao.aoAlternar(empresa.id)}
                      aria-label={`Selecionar ${empresa.name}`}
                      className="accent-acao size-4 align-middle"
                    />
                  </td>
                )}

                <td className="min-w-0 px-3 py-2">
                  <Link
                    href={`/empresas/${empresa.id}`}
                    className="text-tinta hover:text-acao block truncate font-medium"
                    title={empresa.name}
                  >
                    {empresa.name}
                  </Link>
                  {/* A oportunidade vive sob o nome: é o motivo da ligação, e sobe junto com
                      quem vai ligar. Âmbar, porque é o que falta. */}
                  {empresa.opportunities.length > 0 && (
                    <span className="text-lacuna text-legenda mt-0.5 block truncate">
                      {empresa.opportunities.map((o) => o.name).join(" · ")}
                    </span>
                  )}
                </td>

                <td className="text-tinta-media truncate px-3">
                  {empresa.category ?? <Ausente />}
                </td>

                <td className="text-tinta-media px-3 whitespace-nowrap">
                  {empresa.city ? (
                    <>
                      {empresa.city}
                      <span className="text-tinta-fraca">/{empresa.uf}</span>
                    </>
                  ) : (
                    <Ausente />
                  )}
                </td>

                <td className="px-3">
                  <Telefone valor={empresa.phone} />
                </td>

                <td className="px-3">
                  <BotaoWhatsApp numero={empresa.whatsapp} />
                </td>

                <td className="px-3">
                  <SituacaoDoSite empresa={empresa} />
                </td>

                <td className="px-3 text-right">
                  <Score valor={empresa.score} />
                </td>

                <td className="px-3">
                  {empresa.lead_id ? (
                    <Link href={`/leads/${empresa.lead_id}`}>
                      <EtiquetaDeEstagio
                        codigo={empresa.lead_stage_code}
                        nome={empresa.lead_stage_name ?? undefined}
                      />
                    </Link>
                  ) : (
                    <Etiqueta>novo</Etiqueta>
                  )}
                </td>

                <td className="px-3 text-right">
                  <Link
                    href={`/empresas/${empresa.id}`}
                    title={`Abrir ${empresa.name}`}
                    aria-label={`Abrir ${empresa.name}`}
                    className="text-tinta-fraca hover:text-acao hover:bg-papel-fundo inline-flex rounded-sm p-1.5 opacity-0 transition-all group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <ExternalLink size={14} aria-hidden />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * O rótulo do site nunca afirma ausência.
 *
 * "Site oficial não identificado nas fontes analisadas" é a única forma correta — o OSM tem
 * cobertura irregular no interior, e dizer "não tem site" destruiria a credibilidade do
 * diagnóstico inteiro (CLAUDE.md). Aqui aparece encurtado, com o texto completo no `title`.
 */
function SituacaoDoSite({ empresa }: { empresa: Empresa }) {
  if (empresa.website) {
    return (
      <a
        href={empresa.website}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(evento) => evento.stopPropagation()}
        className="text-tinta-media hover:text-acao text-apoio block truncate"
        title={empresa.website}
      >
        {empresa.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
      </a>
    );
  }
  if (empresa.website_status === "NOT_FOUND") {
    return (
      <span title="Site oficial não identificado nas fontes analisadas">
        <Etiqueta tom="lacuna">não identificado</Etiqueta>
      </span>
    );
  }
  return (
    <span
      className="text-tinta-fraca text-apoio"
      title="Ainda não verificamos o site desta empresa"
    >
      não verificado
    </span>
  );
}
