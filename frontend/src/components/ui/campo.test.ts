import { describe, expect, it } from "vitest";

import {
  adicionarFicha,
  filtrarOpcoes,
  moverIndice,
  removerFicha,
  sugestoesRestantes,
  type Opcao,
} from "@/components/ui/campo";

/**
 * As duas peças com lógica de verdade dentro de `Selecao`.
 *
 * O vitest deste projeto roda em `environment: "node"` — não há jsdom nem biblioteca de
 * renderização, e trazer as duas só para exercitar um dropdown sairia caro. Então o que tem
 * regra sai como função pura e é testado aqui, como já se faz com `telefone`.
 */

const RAMOS: Opcao[] = [
  { valor: "1", rotulo: "Óticas" },
  { valor: "2", rotulo: "Açougues" },
  { valor: "3", rotulo: "Farmácias" },
  { valor: "4", rotulo: "Supermercados" },
  { valor: "5", rotulo: "Lojas de roupas" },
  { valor: "6", rotulo: "Concessionárias e revendas de carros" },
];

const rotulos = (opcoes: Opcao[]) => opcoes.map((o) => o.rotulo);

describe("filtrarOpcoes", () => {
  it("acha sem o acento que a pessoa não digita", () => {
    // Ninguém digita "Óticas" com acento numa caixa de busca.
    expect(rotulos(filtrarOpcoes(RAMOS, "otica"))).toEqual(["Óticas"]);
    expect(rotulos(filtrarOpcoes(RAMOS, "acougue"))).toEqual(["Açougues"]);
    expect(rotulos(filtrarOpcoes(RAMOS, "farmacia"))).toEqual(["Farmácias"]);
  });

  it("acha também quando o acento é digitado", () => {
    expect(rotulos(filtrarOpcoes(RAMOS, "óticas"))).toEqual(["Óticas"]);
  });

  it("ignora a caixa", () => {
    expect(rotulos(filtrarOpcoes(RAMOS, "ROUPAS"))).toEqual(["Lojas de roupas"]);
  });

  it("casa no meio da palavra, não só no começo", () => {
    // Quem procura mercado espera achar supermercado; casar por prefixo devolveria vazio.
    expect(rotulos(filtrarOpcoes(RAMOS, "mercado"))).toEqual(["Supermercados"]);
  });

  it("termo vazio ou só espaço devolve tudo", () => {
    expect(filtrarOpcoes(RAMOS, "")).toHaveLength(RAMOS.length);
    expect(filtrarOpcoes(RAMOS, "   ")).toHaveLength(RAMOS.length);
  });

  it("sem correspondência devolve lista vazia, não a lista inteira", () => {
    expect(filtrarOpcoes(RAMOS, "cartorio")).toEqual([]);
  });

  it("não altera a lista recebida", () => {
    filtrarOpcoes(RAMOS, "otica");
    expect(RAMOS).toHaveLength(6);
  });
});

describe("moverIndice", () => {
  it("desce e sobe de um em um", () => {
    expect(moverIndice(0, 5, "ArrowDown")).toBe(1);
    expect(moverIndice(3, 5, "ArrowUp")).toBe(2);
  });

  it("dá a volta nas duas pontas", () => {
    // Sem a volta, chegar ao fim de 49 ramos e ter que subir tudo faz pegar o mouse.
    expect(moverIndice(4, 5, "ArrowDown")).toBe(0);
    expect(moverIndice(0, 5, "ArrowUp")).toBe(4);
  });

  it("Home e End vão às pontas", () => {
    expect(moverIndice(3, 5, "Home")).toBe(0);
    expect(moverIndice(1, 5, "End")).toBe(4);
  });

  it("lista vazia não devolve índice válido", () => {
    // A busca pode não casar com nada; apontar para 0 aqui selecionaria item inexistente.
    expect(moverIndice(0, 0, "ArrowDown")).toBe(-1);
    expect(moverIndice(0, 0, "End")).toBe(-1);
  });

  it("tecla sem efeito não move", () => {
    expect(moverIndice(2, 5, "a")).toBe(2);
  });
});

describe("fichas da escolha múltipla", () => {
  it("adiciona no fim", () => {
    expect(adicionarFicha(["sp"], "campinas")).toEqual(["sp", "campinas"]);
  });

  it("não repete", () => {
    // A mesma cidade reaparece na sugestão seguinte; repetir daria dois `city_ids` iguais.
    expect(adicionarFicha(["sp", "campinas"], "sp")).toEqual(["sp", "campinas"]);
  });

  it("remove pelo valor, não pela posição", () => {
    // Por índice quebraria: a lista muda entre a renderização e o clique.
    expect(removerFicha(["sp", "campinas", "santos"], "campinas")).toEqual(["sp", "santos"]);
  });

  it("remover o que não está lá não muda nada", () => {
    expect(removerFicha(["sp"], "recife")).toEqual(["sp"]);
  });

  it("não sugere o que já é ficha", () => {
    const achadas = [
      { valor: "sp", rotulo: "São Paulo" },
      { valor: "santos", rotulo: "Santos" },
    ];

    expect(sugestoesRestantes(achadas, ["sp"])).toEqual([{ valor: "santos", rotulo: "Santos" }]);
  });

  it("sem nada escolhido, sugere tudo", () => {
    const achadas = [{ valor: "sp", rotulo: "São Paulo" }];

    expect(sugestoesRestantes(achadas, [])).toEqual(achadas);
  });
});
