import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Selecao } from "@/components/ui/campo";

/**
 * O contrato de marcação do gatilho fechado.
 *
 * Não há navegador neste ambiente, e não há jsdom — então interação (abrir, teclar, escolher)
 * **não é verificada por teste**, e isso está registrado como limitação. O que dá para provar
 * sem DOM é o que o servidor renderiza: os papéis ARIA, o rótulo amarrado e o valor exibido.
 * É pouco, mas é o que separa "compila" de "sai certo na página".
 */

const RAMOS = [
  { valor: "1", rotulo: "Padarias" },
  { valor: "2", rotulo: "Óticas" },
];

const render = (elemento: React.ReactElement) => renderToStaticMarkup(elemento);

describe("Selecao fechada", () => {
  it("é um combobox fechado, não um select", () => {
    const html = render(<Selecao rotulo="Ramo" valor="" aoMudar={() => {}} opcoes={RAMOS} />);

    expect(html).toContain('role="combobox"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-haspopup="listbox"');
    expect(html).not.toContain("<select");
  });

  it("veste a mesma classe dos outros controles", () => {
    // É `.entrada` que impõe os 36px. Sem ela o campo deixa de alinhar com o botão ao lado —
    // que era exatamente o defeito da tela de Buscas antes desta troca.
    const html = render(<Selecao rotulo="Ramo" valor="" aoMudar={() => {}} opcoes={RAMOS} />);

    expect(html).toMatch(/class="entrada[^"]*"/);
  });

  it("mostra o rótulo da opção escolhida, não o valor cru", () => {
    const html = render(<Selecao rotulo="Ramo" valor="2" aoMudar={() => {}} opcoes={RAMOS} />);

    expect(html).toContain("Óticas");
  });

  it("amarra rótulo ao controle por id", () => {
    const html = render(<Selecao rotulo="Ramo" valor="" aoMudar={() => {}} opcoes={RAMOS} />);
    const idDoRotulo = html.match(/<label for="([^"]+)"/)?.[1];

    expect(idDoRotulo).toBeTruthy();
    expect(html).toContain(`id="${idDoRotulo}"`);
  });

  it("sem rótulo visível, usa o nome acessível da barra compacta", () => {
    const html = render(
      <Selecao aria-label="Lista de destino" valor="" aoMudar={() => {}} opcoes={RAMOS} />,
    );

    expect(html).toContain('aria-label="Lista de destino"');
  });

  it("a lista só existe depois de abrir", () => {
    const html = render(<Selecao rotulo="Ramo" valor="" aoMudar={() => {}} opcoes={RAMOS} />);

    expect(html).not.toContain('role="listbox"');
    expect(html).not.toContain("Padarias");
  });
});
