"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe, logout, ROLE_LABELS, type Me } from "@/lib/auth";

const SECOES = [
  { href: "/", rotulo: "Radar" },
  { href: "/buscas", rotulo: "Buscas" },
  { href: "/crm", rotulo: "Prospecção" },
  { href: "/configuracoes", rotulo: "Configurações" },
];

/**
 * A casca de toda tela autenticada.
 *
 * Navegação horizontal e enxuta: são quatro seções, e uma barra lateral roubaria largura de
 * uma lista que é o produto inteiro.
 */
export function Casca({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const caminho = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    getMe()
      .then((dados) => {
        if (dados === null) router.replace("/login");
        else setMe(dados);
      })
      .finally(() => setCarregando(false));
  }, [router]);

  if (carregando || !me) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="dados text-tinta-fraca text-sm">carregando…</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-linha bg-papel-alto sticky top-0 z-10 border-b">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3">
          <Link href="/" className="flex items-baseline gap-2">
            <span className="font-display text-tinta text-lg leading-none font-black tracking-tight">
              Radar
            </span>
            <span className="bg-lacuna h-1.5 w-1.5 rounded-full" aria-hidden />
          </Link>

          <nav className="flex gap-1 text-sm" aria-label="Seções">
            {SECOES.map((secao) => {
              const ativa = secao.href === "/" ? caminho === "/" : caminho.startsWith(secao.href);
              return (
                <Link
                  key={secao.href}
                  href={secao.href}
                  aria-current={ativa ? "page" : undefined}
                  className={`rounded px-2.5 py-1 font-medium transition-colors ${
                    ativa
                      ? "bg-papel-fundo text-tinta"
                      : "text-tinta-fraca hover:text-tinta hover:bg-papel"
                  }`}
                >
                  {secao.rotulo}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3 text-sm">
            <div className="text-right leading-tight">
              <div className="text-tinta font-medium">{me.organization?.name ?? "—"}</div>
              <div className="text-tinta-fraca text-xs">
                {me.role ? (ROLE_LABELS[me.role] ?? me.role) : ""}
              </div>
            </div>
            <button
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
              className="border-linha text-tinta-fraca hover:text-tinta hover:border-tinta-fraca rounded border px-2.5 py-1 text-xs font-medium transition-colors"
            >
              Sair
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
    </div>
  );
}

/** Título de tela, com a frase que explica o que se faz ali. */
export function Cabecalho({
  titulo,
  descricao,
  acao,
}: {
  titulo: string;
  descricao?: string;
  acao?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-tinta text-3xl leading-none font-black tracking-tight">
          {titulo}
        </h1>
        {descricao && <p className="text-tinta-fraca mt-2 max-w-xl text-sm">{descricao}</p>}
      </div>
      {acao}
    </div>
  );
}

/**
 * Tela vazia. Nunca é só "nada aqui": diz o que fazer a seguir, porque vazio é convite.
 */
export function Vazio({ titulo, acao }: { titulo: string; acao?: React.ReactNode }) {
  return (
    <div className="border-linha rounded-lg border border-dashed px-6 py-12 text-center">
      <p className="text-tinta-fraca text-sm">{titulo}</p>
      {acao && <div className="mt-4">{acao}</div>}
    </div>
  );
}

export function Erro({ mensagem }: { mensagem: string }) {
  return (
    <p role="alert" className="text-perdido text-sm">
      {mensagem}
    </p>
  );
}

export function Botao({
  children,
  variante = "primaria",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primaria" | "quieta" }) {
  const estilo =
    variante === "primaria"
      ? "bg-acao text-papel-alto hover:bg-acao-forte"
      : "border border-linha text-tinta hover:border-tinta-fraca bg-papel-alto";
  return (
    <button
      {...props}
      className={`rounded px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40 ${estilo} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function Etiqueta({
  children,
  tom = "neutro",
}: {
  children: React.ReactNode;
  tom?: "neutro" | "lacuna" | "ganho" | "perdido";
}) {
  const cores = {
    neutro: "bg-papel-fundo text-tinta-fraca",
    lacuna: "bg-lacuna-fraca text-lacuna",
    ganho: "bg-ganho/10 text-ganho",
    perdido: "bg-perdido/10 text-perdido",
  };
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium tracking-wide ${cores[tom]}`}
    >
      {children}
    </span>
  );
}
