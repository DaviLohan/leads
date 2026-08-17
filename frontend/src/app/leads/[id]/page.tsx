"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Etiqueta, Score } from "@/components/ui/etiqueta";
import { Erro, Esqueleto } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import {
  anotacoesDoLead,
  anotar,
  historicoDoLead,
  leadPorId,
  listarFunis,
  moverLead,
  registrarInteracao,
} from "@/lib/recursos";
import type { Anotacao, Estagio, Interacao, Lead } from "@/lib/tipos";

const TIPOS_DE_CONTATO = [
  ["CALL", "Ligação"],
  ["WHATSAPP", "WhatsApp"],
  ["EMAIL", "E-mail"],
  ["MEETING", "Reunião"],
  ["PROPOSAL", "Proposta"],
] as const;

const RESULTADOS = [
  ["", "Sem resultado"],
  ["NO_ANSWER", "Não atendeu"],
  ["ANSWERED", "Atendeu"],
  ["INTERESTED", "Interessado"],
  ["NOT_INTERESTED", "Sem interesse"],
  ["SCHEDULED", "Agendou"],
] as const;

/**
 * O lead: histórico à esquerda, ações à direita.
 *
 * O histórico é a peça central e vem em ordem cronológica inversa, como se lê um extrato. É
 * append-only no backend, e a tela não oferece editar nem apagar — oferecer o botão para
 * depois recusar seria mentir sobre o que o produto faz.
 */
export default function DetalheDoLead() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<Lead | null>(null);
  const [estagios, setEstagios] = useState<Estagio[]>([]);
  const [historico, setHistorico] = useState<Interacao[]>([]);
  const [anotacoes, setAnotacoes] = useState<Anotacao[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  const recarregar = () =>
    Promise.all([leadPorId(id), historicoDoLead(id), anotacoesDoLead(id)])
      .then(([l, h, a]) => {
        setLead(l);
        setHistorico(h.results);
        setAnotacoes(a.results);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar o lead.")));

  useEffect(() => {
    Promise.all([
      recarregar(),
      listarFunis().then((f) => setEstagios(f.results[0]?.stages ?? [])),
    ]).finally(() => setCarregando(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (carregando) {
    return (
      <Casca>
        <div className="space-y-4">
          <Esqueleto className="h-8 w-64" />
          <Esqueleto className="h-32 w-full" />
        </div>
      </Casca>
    );
  }
  if (!lead) {
    return (
      <Casca>
        <Erro mensagem={erro ?? "Lead não encontrado."} />
      </Casca>
    );
  }

  return (
    <Casca>
      <Link href="/leads" className="text-tinta-fraca hover:text-tinta mb-4 inline-block text-sm">
        ← Leads
      </Link>

      <CabecalhoDaPagina
        titulo={lead.company_name}
        acao={
          <Link href={`/empresas/${lead.company}`}>
            <Botao variante="secundaria">Ver diagnóstico</Botao>
          </Link>
        }
      />

      {erro && <Erro mensagem={erro} />}

      <div className="grid gap-8 lg:grid-cols-[1fr_18rem]">
        <div className="space-y-8">
          <RegistrarContato leadId={id} aoRegistrar={recarregar} />

          <section>
            <h2 className="text-tinta-fraca mb-4 text-xs font-semibold tracking-[0.1em] uppercase">
              Histórico
            </h2>
            <ol className="border-linha space-y-5 border-l pl-5">
              {historico.map((i) => (
                <li key={i.id} className="relative">
                  <span
                    className={`absolute top-1.5 -left-[23px] h-2 w-2 rounded-full ${
                      i.kind === "STATUS_CHANGE" ? "bg-linha" : "bg-acao"
                    }`}
                    aria-hidden
                  />
                  <div className="flex flex-wrap items-baseline gap-x-3">
                    <span className="text-tinta text-sm font-medium">{i.kind_label}</span>
                    <span className="dados text-tinta-fraca text-xs">{quando(i.occurred_at)}</span>
                    {i.outcome && <Etiqueta>{rotuloDoResultado(i.outcome)}</Etiqueta>}
                  </div>
                  {i.description && (
                    <p className="text-tinta-fraca mt-1 text-sm">{i.description}</p>
                  )}
                  {i.author_name && (
                    <p className="text-tinta-fraca/70 mt-1 text-xs">{i.author_name}</p>
                  )}
                </li>
              ))}
            </ol>
          </section>

          <Anotacoes leadId={id} anotacoes={anotacoes} aoAnotar={recarregar} />
        </div>

        <aside className="space-y-6">
          <div className="border-linha bg-papel-alto rounded-lg border p-5">
            <div className="flex items-baseline gap-2">
              <Score valor={lead.score_snapshot} />
              <span className="text-tinta-fraca text-xs">na entrada</span>
            </div>
            {lead.current_score !== null && lead.current_score !== lead.score_snapshot && (
              <p className="text-tinta-fraca mt-2 text-xs">
                Hoje está em <span className="dados text-tinta">{lead.current_score}</span> — a
                empresa mexeu no site desde então.
              </p>
            )}
          </div>

          <div className="border-linha bg-papel-alto rounded-lg border p-5">
            <h2 className="text-tinta-fraca mb-3 text-xs font-semibold tracking-[0.1em] uppercase">
              Estágio
            </h2>
            <div className="space-y-1">
              {estagios.map((e) => (
                <button
                  key={e.id}
                  onClick={async () => {
                    setErro(null);
                    try {
                      await moverLead(lead.id, e.id);
                      await recarregar();
                    } catch (err) {
                      setErro(errorMessage(err, "Não foi possível mover o lead."));
                    }
                  }}
                  aria-current={e.id === lead.stage ? "true" : undefined}
                  className={`block w-full rounded px-2.5 py-1.5 text-left text-sm transition-colors ${
                    e.id === lead.stage
                      ? "bg-acao text-papel-alto font-medium"
                      : "text-tinta-fraca hover:bg-papel hover:text-tinta"
                  }`}
                >
                  {e.name}
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </Casca>
  );
}

function RegistrarContato({ leadId, aoRegistrar }: { leadId: string; aoRegistrar: () => void }) {
  const [kind, setKind] = useState<string>("CALL");
  const [description, setDescription] = useState("");
  const [outcome, setOutcome] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  return (
    <form
      onSubmit={async (evento) => {
        evento.preventDefault();
        setErro(null);
        setEnviando(true);
        try {
          await registrarInteracao(leadId, { kind, description, outcome });
          setDescription("");
          setOutcome("");
          aoRegistrar();
        } catch (e) {
          // Empresa suprimida responde 403: a recusa aparece como é, e não como falha genérica.
          setErro(errorMessage(e, "Não foi possível registrar."));
        } finally {
          setEnviando(false);
        }
      }}
      className="border-linha bg-papel-alto rounded-lg border p-4"
    >
      <div className="flex flex-wrap gap-2">
        {TIPOS_DE_CONTATO.map(([valor, rotulo]) => (
          <button
            key={valor}
            type="button"
            onClick={() => setKind(valor)}
            aria-pressed={kind === valor}
            className={`rounded px-2.5 py-1 text-sm transition-colors ${
              kind === valor
                ? "bg-acao text-papel-alto font-medium"
                : "bg-papel-fundo text-tinta-fraca hover:text-tinta"
            }`}
          >
            {rotulo}
          </button>
        ))}
      </div>

      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        placeholder="O que aconteceu na conversa?"
        className="border-linha mt-3 w-full rounded border px-3 py-2 text-sm"
      />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <select
          value={outcome}
          onChange={(e) => setOutcome(e.target.value)}
          className="border-linha bg-papel-alto rounded border px-2.5 py-1.5 text-sm"
        >
          {RESULTADOS.map(([valor, rotulo]) => (
            <option key={valor} value={valor}>
              {rotulo}
            </option>
          ))}
        </select>
        <Botao type="submit" disabled={enviando}>
          {enviando ? "Registrando…" : "Registrar contato"}
        </Botao>
      </div>

      {erro && <Erro mensagem={erro} className="mt-3" />}
    </form>
  );
}

function Anotacoes({
  leadId,
  anotacoes,
  aoAnotar,
}: {
  leadId: string;
  anotacoes: Anotacao[];
  aoAnotar: () => void;
}) {
  const [texto, setTexto] = useState("");

  return (
    <section>
      <h2 className="text-tinta-fraca mb-3 text-xs font-semibold tracking-[0.1em] uppercase">
        Anotações
      </h2>
      <form
        onSubmit={async (evento) => {
          evento.preventDefault();
          if (!texto.trim()) return;
          await anotar(leadId, texto);
          setTexto("");
          aoAnotar();
        }}
        className="flex gap-2"
      >
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="O que vale lembrar sobre esta empresa?"
          className="border-linha bg-papel-alto flex-1 rounded border px-3 py-1.5 text-sm"
        />
        <Botao variante="secundaria" type="submit">
          Anotar
        </Botao>
      </form>

      {anotacoes.length > 0 && (
        <ul className="mt-4 space-y-3">
          {anotacoes.map((a) => (
            <li key={a.id} className="border-linha border-l-2 pl-3 text-sm">
              <p className="text-tinta">{a.body}</p>
              <p className="text-tinta-fraca/70 dados mt-0.5 text-xs">
                {a.author_email} · {quando(a.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function quando(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function rotuloDoResultado(codigo: string): string {
  return RESULTADOS.find(([valor]) => valor === codigo)?.[1] ?? codigo;
}
