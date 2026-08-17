"use client";

import { useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { Botao } from "@/components/ui/botao";
import { Campo, Selecao } from "@/components/ui/campo";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Erro, Esqueleto, Vazio } from "@/components/ui/superficie";
import { errorMessage, getMe, ROLE_LABELS, type Me } from "@/lib/auth";
import { listarSupressoes, suprimir } from "@/lib/recursos";
import type { Supressao } from "@/lib/tipos";

const TIPOS = [
  ["PHONE", "Telefone", "+554333241000"],
  ["EMAIL", "E-mail", "contato@empresa.com.br"],
  ["DOMAIN", "Domínio", "empresa.com.br"],
  ["TAX_ID", "CNPJ", "11222333000181"],
] as const;

/**
 * Configurações: quem é a organização, e quem ela não pode contatar.
 *
 * A lista de supressão é a peça de conformidade do produto (LGPD), e por isso fica aqui, com
 * o formulário à vista — não escondida atrás de um menu. Não há botão de remover: tirar
 * alguém de um opt-out é decisão que precisa de rastro, e o backend também não oferece.
 */
export default function Configuracoes() {
  const [me, setMe] = useState<Me | null>(null);
  const [supressoes, setSupressoes] = useState<Supressao[]>([]);
  const [carregando, setCarregando] = useState(true);

  const recarregar = () =>
    listarSupressoes()
      .then((p) => setSupressoes(p.results))
      // Só ADMIN enxerga a lista. Para os demais, a ausência não é erro — é permissão.
      .catch(() => setSupressoes([]));

  useEffect(() => {
    Promise.all([getMe().then(setMe), recarregar()]).finally(() => setCarregando(false));
  }, []);

  const podeSuprimir = me?.role === "OWNER" || me?.role === "ADMIN";

  return (
    <Casca>
      <CabecalhoDaPagina titulo="Configurações" />

      <section className="mb-10">
        <h2 className="rotulo-secao mb-3">Organização</h2>
        <dl className="border-linha bg-papel-alto grid gap-x-8 gap-y-3 rounded-lg border p-5 text-sm sm:grid-cols-3">
          <Item rotulo="Nome" valor={me?.organization?.name ?? "—"} />
          <Item rotulo="Seu acesso" valor={me?.role ? (ROLE_LABELS[me.role] ?? me.role) : "—"} />
          <Item rotulo="Fuso" valor={me?.organization?.timezone ?? "—"} />
        </dl>
      </section>

      <section>
        <h2 className="rotulo-secao mb-1">Não contatar</h2>
        <p className="text-tinta-fraca mb-4 max-w-2xl text-sm">
          Quem pediu para não ser abordado. Vale por identificador, não por empresa: o mesmo
          telefone bloqueia a pessoa mesmo que ela reapareça em outra busca. Registrar encerra na
          hora os leads em andamento.
        </p>

        {podeSuprimir && <Formulario aoRegistrar={recarregar} />}

        {carregando ? (
          <div className="mt-4 space-y-2">
            <Esqueleto className="h-10 w-full" />
            <Esqueleto className="h-10 w-full" />
          </div>
        ) : supressoes.length === 0 ? (
          <div className="mt-4">
            <Vazio
              titulo={
                podeSuprimir
                  ? "Nenhum opt-out registrado."
                  : "Só administradores podem ver e registrar opt-outs."
              }
            />
          </div>
        ) : (
          <ul className="border-linha bg-papel-alto divide-linha mt-4 divide-y rounded-lg border">
            {supressoes.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3">
                <span className="text-tinta-fraca w-20 shrink-0 text-xs">
                  {TIPOS.find(([t]) => t === s.identifier_kind)?.[1] ?? s.identifier_kind}
                </span>
                <span className="dados text-tinta text-sm">{s.identifier_value}</span>
                {s.reason && <span className="text-tinta-fraca text-sm">— {s.reason}</span>}
                <span className="dados text-tinta-fraca/70 ml-auto text-xs">
                  {new Date(s.created_at).toLocaleDateString("pt-BR")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Casca>
  );
}

function Formulario({ aoRegistrar }: { aoRegistrar: () => void }) {
  const [kind, setKind] = useState<string>("PHONE");
  const [valor, setValor] = useState("");
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [feito, setFeito] = useState<string | null>(null);

  const exemplo = TIPOS.find(([t]) => t === kind)?.[2] ?? "";

  return (
    <form
      onSubmit={async (evento) => {
        evento.preventDefault();
        setErro(null);
        setFeito(null);
        setEnviando(true);
        try {
          const r = await suprimir({
            identifier_kind: kind,
            identifier_value: valor,
            reason: motivo,
          });
          setValor("");
          setMotivo("");
          setFeito(
            r.leads_encerrados > 0
              ? `Registrado. ${r.leads_encerrados} lead${r.leads_encerrados > 1 ? "s" : ""} encerrado${r.leads_encerrados > 1 ? "s" : ""}.`
              : "Registrado.",
          );
          aoRegistrar();
        } catch (e) {
          setErro(errorMessage(e, "Não foi possível registrar."));
        } finally {
          setEnviando(false);
        }
      }}
      className="border-linha bg-papel-alto flex flex-wrap items-end gap-3 rounded-md border p-4"
    >
      <Selecao
        rotulo="Tipo"
        className="w-44"
        valor={kind}
        aoMudar={setKind}
        opcoes={TIPOS.map(([valor, rotulo]) => ({ valor, rotulo }))}
      />

      <Campo
        rotulo="Identificador"
        className="flex-1"
        mono
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        required
        placeholder={exemplo}
      />

      <Campo
        rotulo="Motivo"
        className="flex-1"
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        placeholder="Pediu para não ser contatado"
      />

      <Botao type="submit" disabled={enviando}>
        {enviando ? "…" : "Registrar"}
      </Botao>

      {erro && <Erro mensagem={erro} className="basis-full" />}
      {feito && <p className="text-acao text-apoio basis-full">{feito}</p>}
    </form>
  );
}

function Item({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-tinta-fraca text-xs">{rotulo}</dt>
      <dd className="text-tinta">{valor}</dd>
    </div>
  );
}
