import { describe, expect, it } from "vitest";

import { formatarTelefone, linkDeWhatsApp } from "./telefone";

describe("formatarTelefone", () => {
  it("formata celular e fixo brasileiros a partir do E.164", () => {
    expect(formatarTelefone("+5541999990000")).toBe("(41) 99999-0000");
    expect(formatarTelefone("+554133330000")).toBe("(41) 3333-0000");
  });

  it("devolve o valor cru quando não reconhece o formato", () => {
    // Melhor mostrar o que a fonte deu do que inventar uma máscara que engana o vendedor.
    expect(formatarTelefone("+14155550000")).toBe("+14155550000");
    expect(formatarTelefone("ramal 22")).toBe("ramal 22");
  });
});

describe("linkDeWhatsApp", () => {
  it("monta o link a partir do número", () => {
    expect(linkDeWhatsApp("+5541999990000")).toBe("https://wa.me/5541999990000");
  });

  it("não existe sem número", () => {
    // A regra do produto: celular não é WhatsApp presumido. Sem contato do tipo WhatsApp,
    // não há botão — em vez de um link que abre conversa com quem não usa o aplicativo.
    expect(linkDeWhatsApp(null)).toBeNull();
    expect(linkDeWhatsApp("1234")).toBeNull();
  });
});
