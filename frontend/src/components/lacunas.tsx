import type { Lacunas } from "@/lib/tipos";
import { ROTULO_LACUNA } from "@/lib/tipos";

/**
 * A barra de lacunas — o elemento que carrega a tese do produto.
 *
 * Cinco segmentos, um por sinal de presença digital. **Cheio de âmbar significa que falta**,
 * e falta é o que se vende. Vazio significa que a empresa já tem, e por isso fica quase
 * invisível: o que já existe não é notícia para quem vai ligar.
 *
 * É o inverso de toda barra de progresso, e é de propósito. Numa lista de trinta empresas,
 * a mais âmbar é a primeira a chamar.
 *
 * Hachurado significa "ainda não verificado". Nunca é pintado como lacuna: "não sei" não
 * vira "não tem", nem aqui nem no backend.
 */
export function BarraDeLacunas({
  lacunas,
  rotulos = false,
}: {
  lacunas: Lacunas;
  rotulos?: boolean;
}) {
  const chaves = Object.keys(ROTULO_LACUNA) as (keyof Lacunas)[];
  const faltando = chaves.filter((c) => lacunas[c] === true).length;
  const desconhecidos = chaves.filter((c) => lacunas[c] === null).length;

  const resumo =
    desconhecidos === chaves.length
      ? "Presença digital ainda não verificada"
      : `${faltando} de ${chaves.length} sinais ausentes`;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-[3px]" role="img" aria-label={resumo}>
        {chaves.map((chave) => {
          const estado = lacunas[chave];
          return (
            <span
              key={chave}
              title={`${ROTULO_LACUNA[chave]}: ${
                estado === null ? "não verificado" : estado ? "falta" : "tem"
              }`}
              className={[
                "h-2 w-7 rounded-xs sm:w-9",
                estado === true
                  ? "bg-lacuna"
                  : estado === false
                    ? "bg-presente/25"
                    : "bg-[repeating-linear-gradient(45deg,var(--color-linha)_0_3px,transparent_3px_6px)]",
              ].join(" ")}
            />
          );
        })}
      </div>
      {rotulos && (
        <div className="flex gap-[3px]">
          {chaves.map((chave) => (
            <span
              key={chave}
              className={[
                "rotulo-lacuna w-7 sm:w-9",
                lacunas[chave] === true ? "text-lacuna" : "text-tinta-fraca/60",
              ].join(" ")}
            >
              {ROTULO_LACUNA[chave]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
