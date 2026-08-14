"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { errorMessage, login } from "@/lib/auth";

/**
 * Entrada.
 *
 * A tela diz de saída o que o produto faz, e diz pela ausência — que é a tese. Não é slogan:
 * é a informação que separa este produto de uma lista de empresas qualquer.
 */
export default function Entrar() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await login(email, senha);
      router.replace("/");
    } catch (falha) {
      setErro(errorMessage(falha, "E-mail ou senha não conferem."));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="flex flex-col justify-center gap-8 px-6 py-16 sm:px-12 lg:px-16">
        <div className="flex items-baseline gap-2">
          <span className="font-display text-tinta text-xl leading-none font-black tracking-tight">
            Radar
          </span>
          <span className="bg-lacuna h-1.5 w-1.5 rounded-full" aria-hidden />
        </div>

        <form onSubmit={aoEnviar} className="flex max-w-sm flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-tinta-fraca text-sm font-medium">E-mail</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="border-linha bg-papel-alto focus:border-acao rounded border px-3 py-2 text-sm outline-none"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-tinta-fraca text-sm font-medium">Senha</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className="border-linha bg-papel-alto focus:border-acao rounded border px-3 py-2 text-sm outline-none"
            />
          </label>

          {erro && (
            <p role="alert" className="text-perdido text-sm">
              {erro}
            </p>
          )}

          <button
            type="submit"
            disabled={enviando}
            className="bg-acao text-papel-alto hover:bg-acao-forte rounded px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <p className="text-tinta-fraca max-w-sm text-xs">
          O acesso é por convite. Fale com quem administra a sua organização.
        </p>
      </section>

      {/* O painel da direita é a tese do produto, dita com o vocabulário do próprio radar:
          cheio de âmbar é o que falta, e é por isso que existe alguém para quem vender. */}
      <section className="bg-papel-fundo hidden flex-col justify-center gap-8 px-16 lg:flex">
        <p className="font-display text-tinta max-w-md text-3xl leading-tight font-black tracking-tight">
          A maioria dos negócios brasileiros não tem site.
          <span className="text-tinta-fraca font-bold"> Este é o mapa de onde eles estão.</span>
        </p>

        <div className="flex flex-col gap-3">
          {[
            ["Clínica Odontológica", [true, true, true, true, false]],
            ["Padaria do Centro", [true, true, false, true, true]],
            ["Auto Peças Trevo", [false, true, true, true, false]],
          ].map(([nome, sinais]) => (
            <div key={nome as string} className="flex items-center gap-4">
              <div className="flex gap-[3px]">
                {(sinais as boolean[]).map((falta, i) => (
                  <span
                    key={i}
                    className={`h-2 w-9 rounded-[2px] ${falta ? "bg-lacuna" : "bg-presente/25"}`}
                  />
                ))}
              </div>
              <span className="text-tinta-fraca text-sm">{nome as string}</span>
            </div>
          ))}
        </div>

        <p className="text-tinta-fraca max-w-md text-sm">
          Cada barra é uma empresa. O que está em âmbar é o que falta — site, versão para celular,
          canal de contato, agendamento, conexão segura. É o que há para vender.
        </p>
      </section>
    </main>
  );
}
