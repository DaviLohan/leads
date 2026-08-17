import { useId } from "react";

/**
 * Campos de formulário.
 *
 * Um componente por tipo, e todos com a mesma anatomia: rótulo acima, controle de 36px,
 * mensagem embaixo. É o que garante que Estado e Cidade, lado a lado, tenham a mesma altura e
 * o mesmo alinhamento de rótulo — coisa que na versão anterior dependia de cada tela repetir
 * seis utilitários corretamente.
 *
 * O `id` é gerado aqui e amarrado ao `<label>`: rótulo clicável e leitor de tela funcionando
 * sem que a tela precise inventar nome de campo.
 */

function Envolucro({
  id,
  rotulo,
  erro,
  ajuda,
  children,
  className = "",
}: {
  id: string;
  rotulo?: string;
  erro?: string;
  ajuda?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex min-w-0 flex-col gap-1.5 ${className}`}>
      {rotulo && (
        <label htmlFor={id} className="text-apoio text-tinta-media font-medium">
          {rotulo}
        </label>
      )}
      {children}
      {/* Erro tem precedência sobre ajuda: mostrar os dois empilha ruído justamente quando a
          pessoa precisa de uma instrução só. */}
      {erro ? (
        <p id={`${id}-msg`} role="alert" className="text-legenda text-perdido">
          {erro}
        </p>
      ) : ajuda ? (
        <p id={`${id}-msg`} className="text-legenda text-tinta-fraca">
          {ajuda}
        </p>
      ) : null}
    </div>
  );
}

export function Campo({
  rotulo,
  erro,
  ajuda,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  rotulo?: string;
  erro?: string;
  ajuda?: string;
}) {
  const id = useId();
  return (
    <Envolucro id={id} rotulo={rotulo} erro={erro} ajuda={ajuda} className={className}>
      <input
        {...props}
        id={id}
        aria-invalid={erro ? true : undefined}
        aria-describedby={erro || ajuda ? `${id}-msg` : undefined}
        className={`entrada ${props.type === "number" ? "dados" : ""}`}
      />
    </Envolucro>
  );
}

export function Selecao({
  rotulo,
  erro,
  ajuda,
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  rotulo?: string;
  erro?: string;
  ajuda?: string;
}) {
  const id = useId();
  return (
    <Envolucro id={id} rotulo={rotulo} erro={erro} ajuda={ajuda} className={className}>
      <select
        {...props}
        id={id}
        aria-invalid={erro ? true : undefined}
        aria-describedby={erro || ajuda ? `${id}-msg` : undefined}
        className="entrada"
      >
        {children}
      </select>
    </Envolucro>
  );
}

/** Caixa de marcação. O rótulo inteiro é a área de clique — alvo de 16px é pequeno demais. */
export function Marcador({
  rotulo,
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { rotulo: string }) {
  return (
    <label
      className={`text-corpo text-tinta flex cursor-pointer items-center gap-2 py-0.5 ${className}`}
    >
      <input type="checkbox" {...props} className="accent-acao size-4 shrink-0" />
      {rotulo}
    </label>
  );
}

/**
 * Dois campos relacionados na mesma linha (Estado | Cidade, score mínimo | máximo).
 *
 * Existe para que a regra "mesma largura, mesma altura, mesmo gap" seja estrutural, e não
 * uma classe que cada tela precisa lembrar de repetir.
 */
export function ParDeCampos({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 items-end gap-3">{children}</div>;
}
