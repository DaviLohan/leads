"use client";

import {
  Bookmark,
  Building2,
  LayoutDashboard,
  LogOut,
  Menu,
  Radar,
  Settings,
  Target,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe, logout, ROLE_LABELS, type Me } from "@/lib/auth";

/**
 * A casca de toda tela autenticada.
 *
 * **Sidebar de 240px**, fixa. A decisão anterior era navegação horizontal, para não roubar
 * largura da tabela; em 1440px sobram 1200px, que é mais do que a tabela precisa, e a barra
 * lateral entrega o que a horizontal não entregava: seis seções legíveis com ícone, estado
 * ativo inequívoco, e um lugar estável para a organização e o usuário.
 *
 * Não há barra superior no desktop **de propósito**. Ela só repetiria o título que o
 * `CabecalhoDaPagina` já mostra, e cada faixa a mais come altura útil de uma tela que existe
 * para listar. No mobile a sidebar vira gaveta, e aí sim aparece uma barra com o botão de menu.
 */

const SECOES = [
  { href: "/", rotulo: "Painel", Icone: LayoutDashboard },
  { href: "/empresas", rotulo: "Empresas", Icone: Building2 },
  { href: "/leads", rotulo: "Leads", Icone: Target },
  { href: "/listas", rotulo: "Listas", Icone: Bookmark },
  { href: "/buscas", rotulo: "Buscas", Icone: Radar },
];

export function Casca({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const caminho = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [menuAberto, setMenuAberto] = useState(false);

  useEffect(() => {
    getMe()
      .then((dados) => {
        if (dados === null) router.replace("/login");
        else setMe(dados);
      })
      .finally(() => setCarregando(false));
  }, [router]);

  // Navegar fecha a gaveta do mobile; sem isto ela fica por cima do conteúdo que a pessoa
  // acabou de pedir.
  useEffect(() => setMenuAberto(false), [caminho]);

  if (carregando || !me) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <span className="border-linha border-t-acao size-5 animate-spin rounded-full border-2" />
        <span className="sr-only">Carregando</span>
      </main>
    );
  }

  return (
    <div className="min-h-screen">
      {/* --- Barra do mobile: só existe abaixo de lg --- */}
      <div className="border-linha bg-papel-alto sticky top-0 z-[var(--z-sticky)] flex h-14 items-center gap-3 border-b px-4 lg:hidden">
        <button
          onClick={() => setMenuAberto(true)}
          aria-label="Abrir menu"
          className="text-tinta-media hover:bg-papel-fundo -ml-2 rounded-sm p-2"
        >
          <Menu size={18} aria-hidden />
        </button>
        <Marca />
      </div>

      {menuAberto && (
        <button
          aria-label="Fechar menu"
          onClick={() => setMenuAberto(false)}
          className="bg-tinta/20 fixed inset-0 z-[var(--z-gaveta)] lg:hidden"
        />
      )}

      {/* --- Sidebar --- */}
      <aside
        className={[
          "border-linha bg-papel-alto fixed inset-y-0 left-0 z-[calc(var(--z-gaveta)+1)]",
          "flex w-[var(--largura-sidebar)] flex-col border-r",
          "transition-transform duration-150 lg:translate-x-0",
          menuAberto ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        <div className="flex h-14 items-center justify-between px-4 lg:h-16">
          <Marca />
          <button
            onClick={() => setMenuAberto(false)}
            aria-label="Fechar menu"
            className="text-tinta-fraca hover:text-tinta rounded-sm p-1 lg:hidden"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-2" aria-label="Seções">
          {SECOES.map((secao) => (
            <ItemDeMenu key={secao.href} {...secao} caminho={caminho} />
          ))}
        </nav>

        {/* Organização e usuário no rodapé: é o dado que responde "estou vendo qual carteira",
            e num produto multi-organização isso não pode ficar escondido. */}
        <div className="border-linha border-t p-3">
          <ItemDeMenu
            href="/configuracoes"
            rotulo="Configurações"
            Icone={Settings}
            caminho={caminho}
          />
          <div className="mt-2 flex items-center gap-2 px-2.5 py-2">
            <div className="min-w-0 flex-1">
              <p className="text-apoio text-tinta truncate font-medium">
                {me.organization?.name ?? "—"}
              </p>
              <p className="text-legenda text-tinta-fraca truncate">
                {me.role ? (ROLE_LABELS[me.role] ?? me.role) : ""}
              </p>
            </div>
            <button
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
              title="Sair"
              aria-label="Sair"
              className="text-tinta-fraca hover:text-tinta hover:bg-papel-fundo shrink-0 rounded-sm p-1.5 transition-colors"
            >
              <LogOut size={15} aria-hidden />
            </button>
          </div>
        </div>
      </aside>

      {/* --- Conteúdo --- */}
      <main className="lg:pl-[var(--largura-sidebar)]">
        <div className="mx-auto max-w-[var(--largura-conteudo)] px-5 py-6 lg:px-8 lg:py-8">
          {children}
        </div>
      </main>
    </div>
  );
}

function Marca() {
  return (
    <Link href="/" className="flex items-baseline gap-1.5">
      <span className="font-display text-tinta text-[1.0625rem] leading-none font-black tracking-tight">
        Radar
      </span>
      {/* O ponto âmbar é a marca: a mesma cor que, na tabela, significa lacuna. */}
      <span className="bg-lacuna-viva size-1.5 rounded-full" aria-hidden />
    </Link>
  );
}

/**
 * Estado ativo: fundo suave, texto forte, ícone na cor de ação e uma barra de 2px na borda.
 * Quatro sinais fracos somam mais clareza que um efeito forte — e nenhum deles depende só de
 * cor, o que mantém o item legível para quem não distingue matiz.
 */
function ItemDeMenu({
  href,
  rotulo,
  Icone,
  caminho,
}: {
  href: string;
  rotulo: string;
  Icone: typeof LayoutDashboard;
  caminho: string;
}) {
  const ativa = href === "/" ? caminho === "/" : caminho.startsWith(href);
  return (
    <Link
      href={href}
      aria-current={ativa ? "page" : undefined}
      className={[
        "text-corpo relative flex h-9 items-center gap-2.5 rounded-sm px-2.5 font-medium transition-colors",
        ativa
          ? "bg-papel-fundo text-tinta"
          : "text-tinta-media hover:bg-papel-fundo/60 hover:text-tinta",
      ].join(" ")}
    >
      {ativa && (
        <span className="bg-acao absolute top-1.5 -left-3 h-6 w-0.5 rounded-r-sm" aria-hidden />
      )}
      <Icone
        size={16}
        strokeWidth={ativa ? 2.25 : 2}
        className={ativa ? "text-acao" : "text-tinta-fraca"}
        aria-hidden
      />
      {rotulo}
    </Link>
  );
}
