import type { NextConfig } from "next";

/**
 * O rewrite de `/api/*` é decisão de arquitetura, não conveniência de desenvolvimento
 * (ADR-0005): o browser enxerga frontend e API na mesma origem, o que torna o cookie de
 * sessão `SameSite=Lax` viável sem afrouxar nada.
 */
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Sem isto o Next remove a barra final (308) e o APPEND_SLASH do Django a devolve (301),
  // em loop infinito. As URLs do Django terminam em "/" por convenção; o rewrite precisa
  // repassá-las intactas.
  skipTrailingSlashRedirect: true,
  // A tela de prospecção virou `/leads`. Link salvo, aba aberta e histórico do navegador
  // continuam funcionando — renomear rota sem redirecionar quebra o usuário, não o código.
  async redirects() {
    return [
      { source: "/crm", destination: "/leads", permanent: false },
      { source: "/crm/:id", destination: "/leads/:id", permanent: false },
    ];
  },
  async rewrites() {
    return [
      // A variante com barra vem primeiro: `:path*` não preserva a barra final ao remontar
      // o destino, e sem ela o Django responde 301 para a URL com barra — loop infinito.
      { source: "/api/:path*/", destination: `${backendUrl}/api/:path*/` },
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/admin/:path*", destination: `${backendUrl}/admin/:path*` },
      { source: "/static/:path*", destination: `${backendUrl}/static/:path*` },
    ];
  },
};

export default nextConfig;
