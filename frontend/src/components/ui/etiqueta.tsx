/**
 * Etiquetas.
 *
 * Regra de cor: **cor só quando significa alguma coisa**. Neutro é o padrão; âmbar é lacuna;
 * verde é ganho; vermelho é perda. Uma tela em que todo estado tem cor própria vira um
 * semáforo onde nada chama atenção.
 */

type Tom = "neutro" | "lacuna" | "ganho" | "perdido" | "aviso" | "info";

const TONS: Record<Tom, string> = {
  neutro: "bg-papel-fundo text-tinta-media",
  lacuna: "bg-lacuna-fraca text-lacuna",
  ganho: "bg-ganho-fraca text-ganho",
  perdido: "bg-perdido-fraca text-perdido",
  aviso: "bg-aviso-fraca text-aviso",
  info: "bg-info-fraca text-info",
};

export function Etiqueta({
  children,
  tom = "neutro",
  className = "",
}: {
  children: React.ReactNode;
  tom?: Tom;
  className?: string;
}) {
  return (
    <span
      className={`text-legenda inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-medium whitespace-nowrap ${TONS[tom]} ${className}`}
    >
      {children}
    </span>
  );
}

/**
 * O estágio do lead no funil.
 *
 * Só ganho e perdido ganham cor. O meio do funil é neutro de propósito: são sete estágios, e
 * sete cores fariam a coluna de status competir com o score, que é o dado que ordena o
 * trabalho.
 */
export function EtiquetaDeEstagio({ codigo, nome }: { codigo: string | null; nome?: string }) {
  if (!codigo) return <Etiqueta>novo</Etiqueta>;
  const tom: Tom =
    codigo === "ganho"
      ? "ganho"
      : codigo === "perdido" || codigo === "nao-contatar"
        ? "perdido"
        : "neutro";
  return <Etiqueta tom={tom}>{nome ?? codigo}</Etiqueta>;
}

/**
 * O score, e o que ele quer dizer.
 *
 * Número em mono (alinha em coluna) mais um ponto de intensidade. Sem arco, sem medidor: a
 * lista tem trinta linhas, e trinta medidores é ruído — o número já é a informação.
 */
export function Score({ valor, tamanho = "md" }: { valor: number | null; tamanho?: "md" | "lg" }) {
  if (valor === null) {
    return (
      <span className="dados text-tinta-fraca/60 text-corpo" title="Ainda não pontuada">
        —
      </span>
    );
  }

  // Os cortes são os do produto: 60+ é fila da frente, 30+ vale a ligação, abaixo disso é
  // trabalho de sobra. Cor só na faixa alta — pintar tudo tira o sinal.
  const alta = valor >= 60;
  const media = valor >= 30;

  return (
    <span className="inline-flex items-center gap-1.5" title={`Score ${valor} de 100`}>
      <span
        className={[
          "dados font-semibold tabular-nums",
          tamanho === "lg" ? "text-display" : "text-corpo",
          alta ? "text-lacuna" : media ? "text-tinta" : "text-tinta-fraca",
        ].join(" ")}
      >
        {valor}
      </span>
      {tamanho === "md" && (
        <span
          aria-hidden
          className={[
            "size-1.5 rounded-full",
            alta ? "bg-lacuna-viva" : media ? "bg-presente" : "bg-linha",
          ].join(" ")}
        />
      )}
    </span>
  );
}
