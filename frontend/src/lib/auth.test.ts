import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { errorMessage } from "./auth";

describe("errorMessage", () => {
  it("usa o campo detail quando existe", () => {
    const erro = new ApiError(401, { detail: "E-mail ou senha inválidos." });
    expect(errorMessage(erro)).toBe("E-mail ou senha inválidos.");
  });

  it("usa o primeiro erro de campo do serializer", () => {
    const erro = new ApiError(400, { new_password: ["Senha curta demais."] });
    expect(errorMessage(erro)).toBe("Senha curta demais.");
  });

  it("cai no texto padrão quando o corpo não é reconhecido", () => {
    expect(errorMessage(new ApiError(500, "boom"), "Falhou.")).toBe("Falhou.");
  });

  it("cai no texto padrão para erro que não é da API", () => {
    expect(errorMessage(new Error("rede"), "Falhou.")).toBe("Falhou.");
  });
});

describe("errorMessage", () => {
  it("lê a mensagem pronta do DRF", () => {
    expect(errorMessage(new ApiError(403, { detail: "Sem permissão." }))).toBe("Sem permissão.");
  });

  it("lê erro de campo simples", () => {
    expect(errorMessage(new ApiError(400, { email: ["E-mail inválido."] }))).toBe(
      "E-mail inválido.",
    );
  });

  it("lê erro aninhado de campo de lista", () => {
    // O formato que o DRF usa quando o campo é ListField — e que a versão anterior desta
    // função não lia, mostrando "não foi possível" no lugar do motivo real.
    expect(
      errorMessage(new ApiError(400, { category_ids: { 0: ["Deve ser um UUID válido."] } })),
    ).toBe("Deve ser um UUID válido.");
  });

  it("cai no texto genérico quando não há nada legível", () => {
    expect(errorMessage(new ApiError(500, {}), "Falhou.")).toBe("Falhou.");
    expect(errorMessage(new Error("rede"), "Falhou.")).toBe("Falhou.");
  });
});

describe("errorMessage não vaza resposta do servidor", () => {
  it("ignora corpo que não é JSON", () => {
    // 500 costuma vir com a página de erro do servidor. Mostrá-la despejaria HTML ou
    // traceback na tela.
    const html = "<!DOCTYPE html><h1>Server Error (500)</h1>";
    expect(errorMessage(new ApiError(500, html), "Falhou.")).toBe("Falhou.");
  });
});
