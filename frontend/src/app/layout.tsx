import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Leads — Radar de Oportunidades",
  description: "Inteligência comercial e prospecção B2B no Brasil",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
