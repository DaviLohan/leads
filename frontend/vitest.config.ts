import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // O mesmo alias do `tsconfig.json`. Sem isto, qualquer módulo testado que importe por
  // `@/...` falha ao resolver — e o teste some da contagem em vez de falhar com clareza.
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
