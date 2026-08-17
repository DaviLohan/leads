"use client";

import { Check, TriangleAlert, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

/**
 * Avisos de ação (toast).
 *
 * Confirmação de ação era, na versão anterior, texto que aparecia dentro do próprio botão ou
 * solto na barra — some junto com o componente e nunca chega a quem estava olhando para a
 * tabela. Aqui é um lugar só, fixo no canto, com o mesmo formato para toda a aplicação.
 *
 * O texto diz **o que aconteceu**, no passado: "Telefone copiado", "3 leads no funil". Nunca
 * "Sucesso!".
 */

type Tipo = "ok" | "erro";
type Aviso = { id: number; texto: string; tipo: Tipo };

const Contexto = createContext<(texto: string, tipo?: Tipo) => void>(() => {});

/** `avisar("Telefone copiado")` de qualquer componente cliente abaixo do provedor. */
export const useAviso = () => useContext(Contexto);

export function ProvedorDeAvisos({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);

  const avisar = useCallback((texto: string, tipo: Tipo = "ok") => {
    const id = Date.now() + Math.random();
    setAvisos((atuais) => [...atuais, { id, texto, tipo }]);
    // Erro fica mais tempo: quem errou precisa ler antes de decidir o que fazer.
    setTimeout(
      () => setAvisos((atuais) => atuais.filter((a) => a.id !== id)),
      tipo === "erro" ? 6000 : 3500,
    );
  }, []);

  const valor = useMemo(() => avisar, [avisar]);

  return (
    <Contexto.Provider value={valor}>
      {children}
      {/* `polite`: o aviso não interrompe quem está lendo a tabela com leitor de tela. */}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-[var(--z-aviso)] flex flex-col gap-2"
      >
        {avisos.map((aviso) => (
          <div
            key={aviso.id}
            className={[
              "pointer-events-auto flex items-center gap-2.5 rounded-md border py-2.5 pr-2 pl-3",
              "shadow-[var(--shadow-suspenso)] motion-safe:animate-[surgir_140ms_ease-out]",
              aviso.tipo === "erro"
                ? "border-perdido/30 bg-perdido-fraca text-perdido"
                : "border-linha bg-papel-alto text-tinta",
            ].join(" ")}
          >
            {aviso.tipo === "erro" ? (
              <TriangleAlert size={15} className="shrink-0" aria-hidden />
            ) : (
              <Check size={15} className="text-ganho shrink-0" aria-hidden />
            )}
            <span className="text-corpo">{aviso.texto}</span>
            <button
              onClick={() => setAvisos((atuais) => atuais.filter((a) => a.id !== aviso.id))}
              title="Fechar"
              aria-label="Fechar aviso"
              className="text-tinta-fraca hover:text-tinta ml-1 rounded-sm p-1 transition-colors"
            >
              <X size={13} aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </Contexto.Provider>
  );
}
