import { describe, expect, it } from "vitest";

import { readCookie } from "./api";

describe("readCookie", () => {
  it("lê o valor pelo nome exato", () => {
    expect(readCookie("csrftoken", "leads_sessionid=abc; csrftoken=xyz")).toBe("xyz");
  });

  it("não confunde nome que é sufixo de outro", () => {
    expect(readCookie("token", "csrftoken=xyz")).toBeNull();
  });

  it("decodifica o valor", () => {
    expect(readCookie("nome", "nome=Jo%C3%A3o")).toBe("João");
  });

  it("devolve null quando o cookie não existe", () => {
    expect(readCookie("ausente", "a=1; b=2")).toBeNull();
  });

  it("aguenta cookie string vazia", () => {
    expect(readCookie("qualquer", "")).toBeNull();
  });
});
