import type { LucideIcon } from "lucide-react";

/**
 * Superfícies e estados de tela.
 *
 * A hierarquia aqui é dada por **borda e fundo**, nunca por sombra: sombra fica reservada ao
 * que flutua de verdade (menu, gaveta, aviso). Cartão com sombra em cima de cartão com sombra
 * é o visual de painel improvisado que este redesign existe para tirar.
 */

export function Cartao({
  children,
  className = "",
  padding = true,
}: {
  children: React.ReactNode;
  className?: string;
  padding?: boolean;
}) {
  return (
    <section
      className={`border-linha bg-papel-alto rounded-md border ${padding ? "p-4" : ""} ${className}`}
    >
      {children}
    </section>
  );
}

/** Cabeçalho interno de cartão: título à esquerda, ação à direita, régua embaixo. */
export function CabecalhoDeCartao({ titulo, acao }: { titulo: string; acao?: React.ReactNode }) {
  return (
    <div className="border-linha -mx-4 -mt-4 mb-4 flex h-12 items-center justify-between border-b px-4">
      <h2 className="rotulo-secao">{titulo}</h2>
      {acao}
    </div>
  );
}

/**
 * Esqueleto de carregamento.
 *
 * Existe para não haver salto de layout: ocupa a mesma altura do conteúdo que vai chegar. A
 * versão anterior escrevia "carregando…" em dez telas e o conteúdo empurrava tudo ao chegar.
 */
export function Esqueleto({ className = "" }: { className?: string }) {
  return <div className={`bg-papel-fundo animate-pulse rounded-sm ${className}`} aria-hidden />;
}

export function EsqueletoDeTabela({
  linhas = 6,
  colunas = 5,
}: {
  linhas?: number;
  colunas?: number;
}) {
  return (
    <div
      className="border-linha bg-papel-alto overflow-hidden rounded-md border"
      role="status"
      aria-label="Carregando resultados"
    >
      <div className="border-linha bg-papel-fundo/60 flex h-10 items-center gap-4 border-b px-4">
        {Array.from({ length: colunas }).map((_, i) => (
          <Esqueleto key={i} className="h-2.5 flex-1" />
        ))}
      </div>
      {Array.from({ length: linhas }).map((_, i) => (
        <div
          key={i}
          className="border-linha flex h-14 items-center gap-4 border-b px-4 last:border-0"
        >
          {Array.from({ length: colunas }).map((_, j) => (
            // A primeira coluna é o nome da empresa: mais larga, como na tabela real.
            <Esqueleto key={j} className={`h-3 ${j === 0 ? "flex-[2]" : "flex-1"}`} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Tela vazia. Nunca é só "nada aqui": diz o que fazer a seguir, porque vazio é convite.
 * O ícone é opcional e discreto — ilustração grande transforma ausência de dado em evento.
 */
export function Vazio({
  titulo,
  descricao,
  Icone,
  acao,
}: {
  titulo: string;
  descricao?: string;
  Icone?: LucideIcon;
  acao?: React.ReactNode;
}) {
  return (
    <div className="border-linha bg-papel-alto/60 flex flex-col items-center rounded-md border border-dashed px-6 py-12 text-center">
      {Icone && (
        <Icone size={20} strokeWidth={1.5} className="text-tinta-fraca/70 mb-3" aria-hidden />
      )}
      <p className="text-corpo text-tinta font-medium">{titulo}</p>
      {descricao && <p className="text-apoio text-tinta-fraca mt-1 max-w-sm">{descricao}</p>}
      {acao && <div className="mt-4">{acao}</div>}
    </div>
  );
}

/**
 * Erro de carregamento.
 *
 * Sempre com saída: mensagem em português e um botão para tentar de novo. Código HTTP e
 * detalhe técnico não chegam aqui — quem lê quer voltar ao trabalho, não depurar.
 */
export function Erro({
  mensagem,
  aoTentarNovamente,
  className = "",
}: {
  mensagem: string;
  aoTentarNovamente?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={`border-perdido/30 bg-perdido-fraca/60 flex flex-wrap items-center gap-3 rounded-md border px-4 py-3 ${className}`}
    >
      <p className="text-corpo text-perdido min-w-0 flex-1">{mensagem}</p>
      {aoTentarNovamente && (
        <button
          onClick={aoTentarNovamente}
          className="text-apoio text-perdido shrink-0 font-medium underline underline-offset-2 hover:no-underline"
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}
