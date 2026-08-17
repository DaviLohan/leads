"use client";

import { Check, ChevronDown, Search } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

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
 *
 * `Selecao` não usa `<select>`: a lista aberta de um select nativo é desenhada pelo sistema
 * operacional — realce azul, fonte do sistema, barra de rolagem do navegador — e **nenhuma
 * regra de CSS alcança**. Trocar o componente é o único caminho para a lista ter a cara do
 * produto. O que se ganha de troco é busca por digitação, que é o que torna 49 ramos (ou 200
 * municípios) navegável.
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
  mono,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  rotulo?: string;
  erro?: string;
  ajuda?: string;
  /** Força a face monoespaçada. Número já vem assim; CNPJ e telefone são texto e precisam pedir. */
  mono?: boolean;
}) {
  const id = useId();
  return (
    <Envolucro id={id} rotulo={rotulo} erro={erro} ajuda={ajuda} className={className}>
      <input
        {...props}
        id={id}
        aria-invalid={erro ? true : undefined}
        aria-describedby={erro || ajuda ? `${id}-msg` : undefined}
        className={`entrada ${mono || props.type === "number" ? "dados" : ""}`}
      />
    </Envolucro>
  );
}

export type Opcao = { valor: string; rotulo: string };

/**
 * Acento fora, caixa baixa.
 *
 * Sem isto, "otica" não acha "Óticas", "acougue" não acha "Açougues" e "farmacia" não acha
 * "Farmácias" — num catálogo em português isso não é refinamento, é a busca não funcionar.
 * `NFD` separa a letra do sinal diacrítico; o range varrido é o bloco de sinais combinantes.
 */
const semAcento = (texto: string) =>
  texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

/**
 * Filtra por trecho em qualquer posição, não por prefixo: quem digita "mercado" espera achar
 * "Supermercados". Função pura e exportada porque é ela que tem lógica de verdade — o teste
 * mora em `campo.test.ts`, sem precisar renderizar nada.
 */
export function filtrarOpcoes(opcoes: Opcao[], termo: string): Opcao[] {
  const alvo = semAcento(termo.trim());
  if (!alvo) return opcoes;
  return opcoes.filter((opcao) => semAcento(opcao.rotulo).includes(alvo));
}

/**
 * Para onde a tecla move o cursor da lista. Dá a volta nas pontas — numa lista de 49, chegar
 * ao fim e ter que subir tudo de novo é o tipo de detalhe que faz usar o mouse.
 */
export function moverIndice(atual: number, total: number, tecla: string): number {
  if (total === 0) return -1;
  switch (tecla) {
    case "ArrowDown":
      return (atual + 1) % total;
    case "ArrowUp":
      return (atual - 1 + total) % total;
    case "Home":
      return 0;
    case "End":
      return total - 1;
    default:
      return atual;
  }
}

// ponytail: acima disto a lista ganha campo de busca. Oito é o que cabe na altura máxima do
// menu sem rolar — passou disso, rolar já é pior que digitar. Não é prop: nenhuma tela
// precisa decidir, e a regra vale igual para 3 opções e para 5.571 municípios.
const OPCOES_ATE_SEM_BUSCA = 8;

export function Selecao({
  rotulo,
  erro,
  ajuda,
  className,
  opcoes,
  valor,
  aoMudar,
  vazio,
  disabled,
  required,
  "aria-label": ariaLabel,
}: {
  rotulo?: string;
  erro?: string;
  ajuda?: string;
  className?: string;
  opcoes: Opcao[];
  valor: string;
  aoMudar: (valor: string) => void;
  /** Rótulo da opção que corresponde a "nenhum filtro" (`valor: ""`). Omitir a suprime. */
  vazio?: string;
  disabled?: boolean;
  required?: boolean;
  /** Nome acessível quando não cabe rótulo visível — barra compacta, por exemplo. */
  "aria-label"?: string;
}) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  const [termo, setTermo] = useState("");
  const [ativo, setAtivo] = useState(0);
  const [paraCima, setParaCima] = useState(false);

  const raiz = useRef<HTMLDivElement>(null);
  const gatilho = useRef<HTMLButtonElement>(null);
  const lista = useRef<HTMLUListElement>(null);

  const todas = vazio !== undefined ? [{ valor: "", rotulo: vazio }, ...opcoes] : opcoes;
  const visiveis = filtrarOpcoes(todas, termo);
  const temBusca = todas.length > OPCOES_ATE_SEM_BUSCA;
  const escolhida = todas.find((o) => o.valor === valor);

  function fechar({ devolverFoco = true } = {}) {
    setAberta(false);
    setTermo("");
    if (devolverFoco) gatilho.current?.focus();
  }

  function escolher(opcao: Opcao) {
    aoMudar(opcao.valor);
    fechar();
  }

  // Clique fora fecha. `mousedown` e não `click`: fechar só no `click` deixa o menu aberto
  // durante a seleção de texto que começou dentro e terminou fora.
  useEffect(() => {
    if (!aberta) return;
    const aoApontar = (evento: MouseEvent) => {
      if (!raiz.current?.contains(evento.target as Node)) fechar({ devolverFoco: false });
    };
    document.addEventListener("mousedown", aoApontar);
    return () => document.removeEventListener("mousedown", aoApontar);
  }, [aberta]);

  // Abre para cima quando não há espaço embaixo. A barra de lote vive colada no rodapé da
  // janela (`sticky bottom-4`): lá o menu para baixo nasceria fora da tela.
  useLayoutEffect(() => {
    if (!aberta) return;
    const caixa = gatilho.current?.getBoundingClientRect();
    if (caixa) setParaCima(window.innerHeight - caixa.bottom < 280 && caixa.top > 280);
  }, [aberta]);

  // A opção sob o cursor tem que estar visível, senão a seta desce para o nada.
  useEffect(() => {
    if (!aberta) return;
    lista.current?.children[ativo]?.scrollIntoView({ block: "nearest" });
  }, [ativo, aberta]);

  function aoTeclar(evento: React.KeyboardEvent) {
    if (!aberta) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(evento.key)) {
        evento.preventDefault();
        setAberta(true);
        setAtivo(
          Math.max(
            0,
            visiveis.findIndex((o) => o.valor === valor),
          ),
        );
      }
      return;
    }
    if (evento.key === "Escape") {
      evento.preventDefault();
      fechar();
    } else if (evento.key === "Tab") {
      fechar({ devolverFoco: false });
    } else if (evento.key === "Enter") {
      evento.preventDefault();
      const alvo = visiveis[ativo];
      if (alvo) escolher(alvo);
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(evento.key)) {
      evento.preventDefault();
      setAtivo(moverIndice(ativo, visiveis.length, evento.key));
    }
  }

  const idLista = `${id}-lista`;
  const idAtiva = visiveis[ativo] ? `${id}-op-${ativo}` : undefined;

  return (
    <Envolucro id={id} rotulo={rotulo} erro={erro} ajuda={ajuda} className={className}>
      <div ref={raiz} className="relative" onKeyDown={aoTeclar}>
        <button
          ref={gatilho}
          type="button"
          id={id}
          role="combobox"
          aria-expanded={aberta}
          aria-controls={aberta ? idLista : undefined}
          aria-haspopup="listbox"
          aria-label={rotulo ? undefined : ariaLabel}
          aria-required={required || undefined}
          aria-invalid={erro ? true : undefined}
          aria-describedby={erro || ajuda ? `${id}-msg` : undefined}
          disabled={disabled}
          onClick={() => {
            if (aberta) return fechar();
            setAberta(true);
            setAtivo(
              Math.max(
                0,
                todas.findIndex((o) => o.valor === valor),
              ),
            );
          }}
          className="entrada flex items-center justify-between gap-2 text-left"
        >
          <span className={`truncate ${escolhida ? "" : "text-tinta-fraca"}`}>
            {escolhida?.rotulo ?? "Escolha…"}
          </span>
          <ChevronDown
            size={16}
            className={`text-tinta-fraca shrink-0 transition-transform ${aberta ? "rotate-180" : ""}`}
            aria-hidden
          />
        </button>

        {aberta && (
          <div
            className={`border-linha bg-papel-alto absolute right-0 left-0 z-[var(--z-dropdown)] overflow-hidden rounded-md border shadow-[var(--shadow-suspenso)] ${
              paraCima ? "bottom-full mb-1" : "top-full mt-1"
            }`}
          >
            {temBusca && (
              <div className="border-linha flex h-[var(--altura-controle)] items-center gap-2 border-b px-2.5">
                <Search size={14} className="text-tinta-fraca shrink-0" aria-hidden />
                <input
                  autoFocus
                  value={termo}
                  onChange={(evento) => {
                    setTermo(evento.target.value);
                    setAtivo(0);
                  }}
                  placeholder="Filtrar…"
                  aria-label="Filtrar opções"
                  aria-controls={idLista}
                  aria-activedescendant={idAtiva}
                  className="text-corpo text-tinta placeholder:text-tinta-fraca min-w-0 flex-1 bg-transparent outline-none"
                />
                {/* Diz se vale continuar digitando ou parar e rolar. Mono como todo número. */}
                <span className="dados text-legenda text-tinta-fraca shrink-0">
                  {visiveis.length}/{todas.length}
                </span>
              </div>
            )}

            <ul
              ref={lista}
              id={idLista}
              role="listbox"
              className="rolagem-fina max-h-72 overflow-y-auto py-1"
            >
              {visiveis.map((opcao, indice) => {
                const atual = opcao.valor === valor;
                return (
                  <li
                    key={opcao.valor || "—"}
                    id={`${id}-op-${indice}`}
                    role="option"
                    aria-selected={atual}
                    onMouseEnter={() => setAtivo(indice)}
                    onClick={() => escolher(opcao)}
                    className={`text-corpo flex h-[var(--altura-controle)] cursor-pointer items-center justify-between gap-2 px-2.5 ${
                      indice === ativo ? "bg-papel-fundo" : ""
                    } ${atual ? "text-acao font-medium" : "text-tinta"}`}
                  >
                    <span className="truncate">{opcao.rotulo}</span>
                    {atual && <Check size={16} className="shrink-0" aria-hidden />}
                  </li>
                );
              })}

              {visiveis.length === 0 && (
                <li className="text-apoio text-tinta-fraca px-2.5 py-3">
                  Nada com “{termo.trim()}”.
                </li>
              )}
            </ul>
          </div>
        )}
      </div>
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
