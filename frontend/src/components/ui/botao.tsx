import type { LucideIcon } from "lucide-react";

/**
 * O botão do produto.
 *
 * Quatro variantes, e a diferença entre elas é **hierarquia**, não decoração: numa tela só
 * uma ação é primária. Antes, todo botão importante era verde sólido e a tela ficava sem
 * ponto de entrada óbvio.
 *
 * A altura vem de `--altura-controle` (36px), a mesma do campo e do select. É isso que faz
 * botão e input alinharem quando ficam lado a lado numa barra de filtros — o desalinhamento
 * mais visível da versão anterior.
 */

type Variante = "primaria" | "secundaria" | "quieta" | "perigo";

const VARIANTES: Record<Variante, string> = {
  // Ação principal da tela. Uma por tela.
  primaria: "bg-acao text-papel-alto hover:bg-acao-forte border border-transparent",
  // Ação de apoio: mesma importância visual de um campo, por isso mesma borda.
  secundaria:
    "bg-papel-alto text-tinta border border-linha hover:border-linha-forte hover:bg-papel",
  // Terciária: só texto até o mouse chegar. Para ações repetidas numa linha de tabela.
  quieta: "bg-transparent text-tinta-media border border-transparent hover:bg-papel-fundo",
  // Destrutiva: contida, não vermelha sólida — vermelho sólido pede o clique que queremos evitar.
  perigo:
    "bg-papel-alto text-perdido border border-perdido/30 hover:bg-perdido-fraca hover:border-perdido/50",
};

export function Botao({
  children,
  variante = "secundaria",
  tamanho = "md",
  Icone,
  carregando = false,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: Variante;
  tamanho?: "md" | "lg";
  Icone?: LucideIcon;
  carregando?: boolean;
}) {
  const altura =
    tamanho === "lg" ? "h-[var(--altura-controle-lg)] px-4" : "h-[var(--altura-controle)] px-3";

  return (
    <button
      {...props}
      disabled={props.disabled || carregando}
      aria-busy={carregando || undefined}
      className={[
        "inline-flex shrink-0 items-center justify-center gap-2 rounded-sm text-corpo font-medium",
        "transition-colors duration-100",
        "disabled:pointer-events-none disabled:opacity-45",
        altura,
        VARIANTES[variante],
        className,
      ].join(" ")}
    >
      {/* Ícone a 16px sempre: acima disso compete com o rótulo, abaixo some. */}
      {Icone && !carregando && <Icone size={16} strokeWidth={2} aria-hidden />}
      {carregando && (
        <span
          className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden
        />
      )}
      {children}
    </button>
  );
}

/**
 * Botão só de ícone. Exige `title` — ícone sem nome acessível é botão mudo para quem usa
 * leitor de tela, e é o erro mais comum em barra de ações de tabela.
 */
export function BotaoDeIcone({
  Icone,
  title,
  variante = "quieta",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  Icone: LucideIcon;
  title: string;
  variante?: Variante;
}) {
  return (
    <button
      {...props}
      title={title}
      aria-label={title}
      className={[
        "inline-flex size-9 shrink-0 items-center justify-center rounded-sm",
        "transition-colors duration-100 disabled:pointer-events-none disabled:opacity-45",
        VARIANTES[variante],
        className,
      ].join(" ")}
    >
      <Icone size={16} strokeWidth={2} aria-hidden />
    </button>
  );
}
