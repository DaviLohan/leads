import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // O mesmo alias do `tsconfig.json`. Sem isto, qualquer módulo testado que importe por
  // `@/...` falha ao resolver — e o teste some da contagem em vez de falhar com clareza.
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // O Next compila JSX com o runtime automático; o vitest, por omissão, com o clássico
  // (`React.createElement`). Sem alinhar os dois, componente que não importa `React` — que é
  // a convenção do projeto inteiro — quebra com "React is not defined" **só no teste**,
  // enquanto funciona no navegador.
  esbuild: { jsx: "automatic" },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
