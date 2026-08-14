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
