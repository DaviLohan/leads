import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

/**
 * Cabeçalho de página: título, uma frase, ação principal à direita.
 *
 * Estrutura fixa em todas as telas — é o que responde, em um olhar, "onde estou" e "qual é a
 * ação principal aqui". Na versão anterior cada tela montava o seu, com tamanhos de título
 * diferentes (`2xl` numa, `3xl` noutra) e a ação ora à direita, ora embaixo.
 */
export function CabecalhoDaPagina({
  titulo,
  descricao,
  acao,
  voltar,
  contador,
}: {
  titulo: string;
  descricao?: string;
  acao?: React.ReactNode;
  /** Link de retorno, para telas de detalhe. */
  voltar?: { href: string; rotulo: string };
  /** Número ao lado do título — "347 empresas". Fica em mono, como todo dado. */
  contador?: string;
}) {
  return (
    <header className="mb-6">
      {voltar && (
        <Link
          href={voltar.href}
          className="text-apoio text-tinta-fraca hover:text-tinta mb-3 inline-flex items-center gap-1 transition-colors"
        >
          <ChevronLeft size={14} aria-hidden />
          {voltar.rotulo}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2.5">
            <h1 className="font-display text-titulo text-tinta font-bold tracking-tight">
              {titulo}
            </h1>
            {contador && <span className="dados text-apoio text-tinta-fraca">{contador}</span>}
          </div>
          {descricao && <p className="text-apoio text-tinta-fraca mt-1 max-w-2xl">{descricao}</p>}
        </div>
        {acao && <div className="flex shrink-0 flex-wrap items-center gap-2">{acao}</div>}
      </div>
    </header>
  );
}

/**
 * Cartão de métrica do painel.
 *
 * Rótulo, valor e contexto — nesta ordem, porque é a ordem da leitura. Sem ícone gigante e
 * sem gráfico decorativo: o número é a informação, e um ícone de 40px ao lado só disputa
 * espaço com ele.
 */
export function CartaoDeMetrica({
  rotulo,
  valor,
  contexto,
  destaque = false,
  Icone,
}: {
  rotulo: string;
  valor: number | string;
  contexto?: string;
  /** Um por painel, no máximo: é o número que precisa incomodar. */
  destaque?: boolean;
  Icone?: LucideIcon;
}) {
  return (
    <div className="bg-papel-alto flex flex-col gap-1 px-4 py-3.5">
      <div className="text-tinta-fraca flex items-center gap-1.5">
        {Icone && <Icone size={13} strokeWidth={2} aria-hidden />}
        <span className="text-legenda font-medium tracking-wide uppercase">{rotulo}</span>
      </div>
      <span
        className={`dados text-display font-semibold ${
          destaque && valor !== 0 ? "text-lacuna" : "text-tinta"
        }`}
      >
        {valor}
      </span>
      {contexto && <span className="text-legenda text-tinta-fraca">{contexto}</span>}
    </div>
  );
}
