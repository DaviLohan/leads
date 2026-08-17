"use client";

import { Check, ChevronDown, Search, X } from "lucide-react";
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

/**
 * Junta as fichas já escolhidas com a nova, sem repetir.
 *
 * A repetição é fácil de produzir — a mesma cidade aparece de novo na sugestão seguinte — e
 * daria dois `city_ids` iguais no critério da busca.
 */
export function adicionarFicha(atuais: string[], novo: string): string[] {
  return atuais.includes(novo) ? atuais : [...atuais, novo];
}

/** Tira a ficha pelo valor. Remover por índice quebra quando a lista muda entre o clique. */
export function removerFicha(atuais: string[], alvo: string): string[] {
  return atuais.filter((valor) => valor !== alvo);
}

/** O que ainda dá para sugerir: fora o que já virou ficha. */
export function sugestoesRestantes(opcoes: Opcao[], escolhidos: string[]): Opcao[] {
  return opcoes.filter((opcao) => !escolhidos.includes(opcao.valor));
}

// ponytail: acima disto a lista ganha campo de busca. Oito é o que cabe na altura máxima do
// menu sem rolar — passou disso, rolar já é pior que digitar. Não é prop: nenhuma tela
// precisa decidir, e a regra vale igual para 3 opções e para 5.571 municípios.
const OPCOES_ATE_SEM_BUSCA = 8;

/** Espera entre a tecla e a ida ao servidor. Curto o bastante para não parecer travado. */
const ESPERA_DA_BUSCA = 250;

/**
 * A mecânica da lista flutuante, compartilhada por `Selecao` e `SelecaoMultipla`.
 *
 * Abrir, fechar ao clicar fora, virar para cima quando falta espaço e manter a opção ativa à
 * vista são as mesmas quatro coisas nos dois — e duplicá-las seria duplicar justamente a parte
 * que erra em silêncio.
 */
function useListaFlutuante(ativo: number) {
  const [aberta, setAberta] = useState(false);
  const [paraCima, setParaCima] = useState(false);

  const raiz = useRef<HTMLDivElement>(null);
  const gatilho = useRef<HTMLElement>(null);
  const lista = useRef<HTMLUListElement>(null);

  // Clique fora fecha. `mousedown` e não `click`: fechar só no `click` deixa o menu aberto
  // durante a seleção de texto que começou dentro e terminou fora.
  useEffect(() => {
    if (!aberta) return;
    const aoApontar = (evento: MouseEvent) => {
      if (!raiz.current?.contains(evento.target as Node)) setAberta(false);
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

  return { aberta, setAberta, paraCima, raiz, gatilho, lista };
}

/**
 * Busca no servidor enquanto se digita, quando a lista não cabe no cliente.
 *
 * Municípios são 5.571 e a API pagina em 200 (`core/pagination.py`), então em 10 dos 27
 * estados filtrar localmente esconde a maioria das cidades — sem erro nenhum. Devolve as
 * opções recebidas e se ainda está esperando.
 */
function useBuscaRemota(termo: string, aoBuscar?: (termo: string) => Promise<Opcao[]>) {
  const [remotas, setRemotas] = useState<Opcao[]>([]);
  const [buscando, setBuscando] = useState(false);

  // A função guardada em ref, e **fora** das dependências do efeito: quem chama a define no
  // corpo do componente, então ela é outra a cada render. Deixá-la nas dependências faria o
  // efeito rodar de novo a cada resposta, que causa outro render — laço infinito batendo no
  // servidor. A ref mantém sempre a versão mais recente sem reagendar nada.
  const referencia = useRef(aoBuscar);
  referencia.current = aoBuscar;

  useEffect(() => {
    if (!referencia.current) return;
    // `valido` mora aqui, e não dentro do `setTimeout`: o retorno da callback de um timer é
    // descartado, então cancelar lá dentro não cancelaria nada. Sem esta guarda, a resposta
    // de "camp" chega depois da de "campin" e sobrescreve a lista certa pela antiga.
    let valido = true;
    setBuscando(true);
    const relogio = setTimeout(() => {
      referencia.current!(termo)
        .then((achadas) => valido && setRemotas(achadas))
        .catch(() => valido && setRemotas([]))
        .finally(() => valido && setBuscando(false));
    }, ESPERA_DA_BUSCA);
    return () => {
      valido = false;
      clearTimeout(relogio);
    };
  }, [termo]);

  return { remotas, buscando };
}

/** A lista de opções do menu: do servidor quando há busca remota, filtrada aqui quando não. */
function opcoesVisiveis(
  todas: Opcao[],
  termo: string,
  remoto: { ativo: boolean; opcoes: Opcao[] },
): Opcao[] {
  return remoto.ativo ? remoto.opcoes : filtrarOpcoes(todas, termo);
}

export function Selecao({
  rotulo,
  erro,
  ajuda,
  className,
  opcoes,
  valor,
  aoMudar,
  aoBuscar,
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
  /** Busca no servidor. Com ela, `opcoes` serve só para saber o rótulo do valor atual. */
  aoBuscar?: (termo: string) => Promise<Opcao[]>;
  /** Rótulo da opção que corresponde a "nenhum filtro" (`valor: ""`). Omitir a suprime. */
  vazio?: string;
  disabled?: boolean;
  required?: boolean;
  /** Nome acessível quando não cabe rótulo visível — barra compacta, por exemplo. */
  "aria-label"?: string;
}) {
  const id = useId();
  const [termo, setTermo] = useState("");
  const [ativo, setAtivo] = useState(0);
  const { aberta, setAberta, paraCima, raiz, gatilho, lista } = useListaFlutuante(ativo);
  const { remotas, buscando } = useBuscaRemota(aberta && aoBuscar ? termo : "", aoBuscar);

  const todas = vazio !== undefined ? [{ valor: "", rotulo: vazio }, ...opcoes] : opcoes;
  const visiveis = opcoesVisiveis(todas, termo, { ativo: Boolean(aoBuscar), opcoes: remotas });
  const temBusca = Boolean(aoBuscar) || todas.length > OPCOES_ATE_SEM_BUSCA;
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

  return (
    <Envolucro id={id} rotulo={rotulo} erro={erro} ajuda={ajuda} className={className}>
      <div ref={raiz} className="relative" onKeyDown={aoTeclar}>
        <button
          ref={gatilho as React.RefObject<HTMLButtonElement>}
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
          <ListaFlutuante
            idLista={idLista}
            idPrefixo={id}
            paraCima={paraCima}
            refLista={lista}
            opcoes={visiveis}
            ativo={ativo}
            setAtivo={setAtivo}
            aoEscolher={escolher}
            selecionado={(opcao) => opcao.valor === valor}
            busca={
              temBusca
                ? {
                    termo,
                    setTermo: (novo) => {
                      setTermo(novo);
                      setAtivo(0);
                    },
                    buscando,
                    contagem: aoBuscar ? null : `${visiveis.length}/${todas.length}`,
                  }
                : null
            }
          />
        )}
      </div>
    </Envolucro>
  );
}

/**
 * Escolha de vários, com fichas. É o campo de municípios da busca.
 *
 * **Não é lista de caixas de marcação**, e a diferença importa: entre os 645 municípios de São
 * Paulo ninguém rola marcando. Aqui se digita, escolhe, e o escolhido vira ficha — a lista
 * continua aberta para o próximo, e o campo se limpa sozinho.
 */
export function SelecaoMultipla({
  rotulo,
  erro,
  ajuda,
  className,
  opcoes,
  valores,
  aoMudar,
  aoBuscar,
  rotulosConhecidos,
  disabled,
  espaco = "Digite para procurar",
}: {
  rotulo?: string;
  erro?: string;
  ajuda?: string;
  className?: string;
  opcoes: Opcao[];
  valores: string[];
  aoMudar: (valores: string[]) => void;
  aoBuscar?: (termo: string) => Promise<Opcao[]>;
  /** Rótulo de cada valor já escolhido — com busca remota, ele não está mais em `opcoes`. */
  rotulosConhecidos?: Record<string, string>;
  disabled?: boolean;
  espaco?: string;
}) {
  const id = useId();
  const [termo, setTermo] = useState("");
  const [ativo, setAtivo] = useState(0);
  const { aberta, setAberta, paraCima, raiz, gatilho, lista } = useListaFlutuante(ativo);
  const { remotas, buscando } = useBuscaRemota(aberta && aoBuscar ? termo : "", aoBuscar);

  const encontradas = opcoesVisiveis(opcoes, termo, {
    ativo: Boolean(aoBuscar),
    opcoes: remotas,
  });
  const visiveis = sugestoesRestantes(encontradas, valores);

  function escolher(opcao: Opcao) {
    aoMudar(adicionarFicha(valores, opcao.valor));
    setTermo("");
    setAtivo(0);
    gatilho.current?.focus();
  }

  function aoTeclar(evento: React.KeyboardEvent) {
    if (evento.key === "Escape") {
      evento.preventDefault();
      setAberta(false);
    } else if (evento.key === "Enter") {
      // Sem isto, Enter no campo envia o formulário da busca em vez de escolher a cidade.
      evento.preventDefault();
      const alvo = visiveis[ativo];
      if (alvo) escolher(alvo);
    } else if (evento.key === "Backspace" && !termo && valores.length) {
      // Apagar com o campo vazio tira a última ficha: é o que a mão espera de um campo assim.
      aoMudar(valores.slice(0, -1));
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(evento.key)) {
      evento.preventDefault();
      setAberta(true);
      setAtivo(moverIndice(ativo, visiveis.length, evento.key));
    }
  }

  const idLista = `${id}-lista`;
  const rotuloDe = (valor: string) =>
    rotulosConhecidos?.[valor] ?? opcoes.find((o) => o.valor === valor)?.rotulo ?? valor;

  return (
    <Envolucro id={id} rotulo={rotulo} erro={erro} ajuda={ajuda} className={className}>
      <div ref={raiz} className="relative" onKeyDown={aoTeclar}>
        {/* A caixa cresce com as fichas, então não usa `.entrada` (altura fixa de 36px) — mas
            repete borda, fundo e raio para ser o mesmo controle aos olhos. */}
        <div className="entrada-fichas" data-desabilitado={disabled || undefined}>
          {valores.map((valor) => (
            <span
              key={valor}
              className="bg-papel-fundo text-tinta text-apoio flex items-center gap-1 rounded-sm py-0.5 pr-1 pl-1.5"
            >
              {rotuloDe(valor)}
              <button
                type="button"
                onClick={() => aoMudar(removerFicha(valores, valor))}
                title={`Remover ${rotuloDe(valor)}`}
                className="text-tinta-fraca hover:text-perdido"
              >
                <X size={12} aria-hidden />
              </button>
            </span>
          ))}

          <input
            ref={gatilho as React.RefObject<HTMLInputElement>}
            id={id}
            role="combobox"
            aria-expanded={aberta}
            aria-controls={aberta ? idLista : undefined}
            aria-haspopup="listbox"
            aria-invalid={erro ? true : undefined}
            aria-describedby={erro || ajuda ? `${id}-msg` : undefined}
            disabled={disabled}
            value={termo}
            placeholder={valores.length ? "" : espaco}
            onFocus={() => setAberta(true)}
            onChange={(evento) => {
              setTermo(evento.target.value);
              setAtivo(0);
              setAberta(true);
            }}
            className="text-corpo text-tinta placeholder:text-tinta-fraca min-w-24 flex-1 bg-transparent px-1 py-0.5 outline-none"
          />
        </div>

        {aberta && (termo || visiveis.length > 0) && (
          <ListaFlutuante
            idLista={idLista}
            idPrefixo={id}
            paraCima={paraCima}
            refLista={lista}
            opcoes={visiveis}
            ativo={ativo}
            setAtivo={setAtivo}
            aoEscolher={escolher}
            selecionado={() => false}
            busca={null}
            buscandoRemoto={buscando}
          />
        )}
      </div>
    </Envolucro>
  );
}

/** O menu em si — a parte que as duas seleções desenham igual. */
function ListaFlutuante({
  idLista,
  idPrefixo,
  paraCima,
  refLista,
  opcoes,
  ativo,
  setAtivo,
  aoEscolher,
  selecionado,
  busca,
  buscandoRemoto = false,
}: {
  idLista: string;
  idPrefixo: string;
  paraCima: boolean;
  refLista: React.RefObject<HTMLUListElement | null>;
  opcoes: Opcao[];
  ativo: number;
  setAtivo: (indice: number) => void;
  aoEscolher: (opcao: Opcao) => void;
  selecionado: (opcao: Opcao) => boolean;
  busca: {
    termo: string;
    setTermo: (termo: string) => void;
    buscando: boolean;
    contagem: string | null;
  } | null;
  buscandoRemoto?: boolean;
}) {
  const esperando = busca?.buscando || buscandoRemoto;

  return (
    <div
      className={`border-linha bg-papel-alto absolute right-0 left-0 z-[var(--z-dropdown)] overflow-hidden rounded-md border shadow-[var(--shadow-suspenso)] ${
        paraCima ? "bottom-full mb-1" : "top-full mt-1"
      }`}
    >
      {busca && (
        <div className="border-linha flex h-[var(--altura-controle)] items-center gap-2 border-b px-2.5">
          <Search size={14} className="text-tinta-fraca shrink-0" aria-hidden />
          <input
            autoFocus
            value={busca.termo}
            onChange={(evento) => busca.setTermo(evento.target.value)}
            placeholder="Filtrar…"
            aria-label="Filtrar opções"
            aria-controls={idLista}
            className="text-corpo text-tinta placeholder:text-tinta-fraca min-w-0 flex-1 bg-transparent outline-none"
          />
          {/* Diz se vale continuar digitando ou parar e rolar. Mono como todo número. */}
          {busca.contagem && (
            <span className="dados text-legenda text-tinta-fraca shrink-0">{busca.contagem}</span>
          )}
        </div>
      )}

      <ul
        ref={refLista}
        id={idLista}
        role="listbox"
        className="rolagem-fina max-h-72 overflow-y-auto py-1"
      >
        {opcoes.map((opcao, indice) => {
          const atual = selecionado(opcao);
          return (
            <li
              key={opcao.valor || "—"}
              id={`${idPrefixo}-op-${indice}`}
              role="option"
              aria-selected={atual}
              onMouseEnter={() => setAtivo(indice)}
              onClick={() => aoEscolher(opcao)}
              className={`text-corpo flex h-[var(--altura-controle)] cursor-pointer items-center justify-between gap-2 px-2.5 ${
                indice === ativo ? "bg-papel-fundo" : ""
              } ${atual ? "text-acao font-medium" : "text-tinta"}`}
            >
              <span className="truncate">{opcao.rotulo}</span>
              {atual && <Check size={16} className="shrink-0" aria-hidden />}
            </li>
          );
        })}

        {opcoes.length === 0 && (
          <li className="text-apoio text-tinta-fraca px-2.5 py-3">
            {esperando ? "Procurando…" : "Nada encontrado."}
          </li>
        )}
      </ul>
    </div>
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
