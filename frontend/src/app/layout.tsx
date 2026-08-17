import type { Metadata } from "next";
import { Archivo, Azeret_Mono, Chivo } from "next/font/google";

import { ProvedorDeAvisos } from "@/components/ui/aviso";

import "./globals.css";

/**
 * Três papéis, três famílias.
 *
 * Chivo (Omnibus-Type, fundição latino-americana) faz os títulos: grotesca de hastes fortes,
 * com personalidade suficiente para carregar um número grande sozinha.
 *
 * Archivo é o corpo — quieta, feita para interface densa, com diacrítico do português bem
 * resolvido em corpo pequeno.
 *
 * Azeret Mono é o dado: score, telefone, código IBGE, contagem. Números tabulares alinhados
 * em coluna são o que permite varrer uma lista de ligações com o olho, sem ler.
 */
const display = Chivo({
  subsets: ["latin"],
  weight: ["700", "900"],
  variable: "--fonte-display",
  display: "swap",
});

const corpo = Archivo({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--fonte-corpo",
  display: "swap",
});

const dados = Azeret_Mono({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--fonte-dados",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Radar de Oportunidades",
  description: "Onde falta presença digital no Brasil — e quem vender para.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${display.variable} ${corpo.variable} ${dados.variable}`}>
      <body className="min-h-screen antialiased">
        {/* Um provedor só para toda a aplicação: confirmação de ação aparece sempre no mesmo
            canto, com o mesmo formato, venha de qual tela vier. */}
        <ProvedorDeAvisos>{children}</ProvedorDeAvisos>
      </body>
    </html>
  );
}
