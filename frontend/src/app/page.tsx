"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe, logout, ROLE_LABELS, type Me } from "@/lib/auth";

/**
 * Home autenticada da fundação. Prova, no browser, o ciclo completo de sessão via cookie
 * HTTPOnly (ADR-0005). O Dashboard de verdade entra na Etapa 13.
 */
export default function Home() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    getMe()
      .then((dados) => {
        if (dados === null) {
          router.replace("/login");
          return;
        }
        setMe(dados);
      })
      .finally(() => setCarregando(false));
  }, [router]);

  async function sair() {
    await logout();
    router.replace("/login");
  }

  if (carregando || !me) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-neutral-500">Carregando…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Radar de Oportunidades</h1>
        <p className="mt-2 text-neutral-500">Inteligência comercial e prospecção B2B no Brasil.</p>
      </div>

      <dl className="grid gap-3 rounded-lg border border-neutral-200 p-4 text-sm dark:border-neutral-800">
        <div className="flex justify-between gap-4">
          <dt className="text-neutral-500">Usuário</dt>
          <dd className="font-medium">{me.user.full_name || me.user.email}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-neutral-500">Organização</dt>
          <dd className="font-medium">
            {me.organization ? me.organization.name : "nenhuma organização ativa"}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-neutral-500">Papel</dt>
          <dd className="font-medium">{me.role ? (ROLE_LABELS[me.role] ?? me.role) : "—"}</dd>
        </div>
      </dl>

      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-neutral-500">
          Etapa 3 concluída. Geografia e empresas vêm a seguir.
        </p>
        <button
          onClick={sair}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium dark:border-neutral-700"
        >
          Sair
        </button>
      </div>
    </main>
  );
}
