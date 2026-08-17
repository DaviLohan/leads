"use client";

import { Bookmark, Target, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/ui/aviso";
import { Botao } from "@/components/ui/botao";
import { errorMessage } from "@/lib/auth";
import { adicionarNaLista, criarLeadsEmLote, criarLista, listarListas } from "@/lib/recursos";
import type { Lista } from "@/lib/tipos";

/**
 * A barra que aparece quando há empresas selecionadas.
 *
 * Duas ações, e a diferença entre elas é o ponto: **salvar em lista** apenas separa um lote
 * para trabalhar depois; **adicionar ao CRM** cria relação comercial, abre histórico e passa
 * pela supressão da LGPD. A segunda é irreversível de fato — o histórico não se apaga —, e por
 * isso é a primária, com o resultado relatado inteiro, inclusive quem ficou de fora.
 *
 * A barra é fixa no rodapé enquanto houver seleção: rolar 200 linhas escolhendo empresas e
 * ter que voltar ao topo para agir é o tipo de detalhe que faz uma ferramenta parecer lenta.
 */
export function BarraDeLote({
  selecionadas,
  aoConcluir,
}: {
  selecionadas: string[];
  aoConcluir: () => void;
}) {
  const avisar = useAviso();
  const [listas, setListas] = useState<Lista[]>([]);
  const [destino, setDestino] = useState("");
  const [nova, setNova] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    listarListas().then((p) => setListas(p.results));
  }, []);

  if (selecionadas.length === 0) return null;

  async function salvarEmLista() {
    setOcupado(true);
    try {
      const lista = nova.trim()
        ? await criarLista(nova.trim())
        : listas.find((l) => l.id === destino);
      if (!lista) {
        avisar("Escolha uma lista ou dê um nome para a nova.", "erro");
        return;
      }
      const r = await adicionarNaLista(lista.id, selecionadas);
      avisar(
        `${r.adicionados} em "${lista.name}"` +
          (r.ja_estavam ? ` · ${r.ja_estavam} já estava(m)` : ""),
      );
      setNova("");
      setListas((await listarListas()).results);
      aoConcluir();
    } catch (e) {
      avisar(errorMessage(e, "Não foi possível salvar na lista."), "erro");
    } finally {
      setOcupado(false);
    }
  }

  async function mandarParaOCrm() {
    setOcupado(true);
    try {
      const r = await criarLeadsEmLote(selecionadas);
      const partes = [`${r.criados} no funil`];
      if (r.ja_existiam) partes.push(`${r.ja_existiam} já estava(m)`);
      // Nunca em silêncio: quem selecionou precisa saber quem a LGPD deixou de fora.
      if (r.suprimidos.length) {
        partes.push(`${r.suprimidos.length} recusada(s) por opt-out`);
      }
      avisar(partes.join(" · "), r.suprimidos.length ? "erro" : "ok");
      aoConcluir();
    } catch (e) {
      avisar(errorMessage(e, "Não foi possível criar os leads."), "erro");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="sticky bottom-4 z-[var(--z-sticky)]">
      <div className="border-acao/25 bg-papel-alto flex flex-wrap items-center gap-3 rounded-md border p-2.5 shadow-[var(--shadow-suspenso)]">
        <span className="text-corpo text-tinta pl-1.5 font-medium">
          <span className="dados">{selecionadas.length}</span> selecionada
          {selecionadas.length > 1 ? "s" : ""}
        </span>

        <div className="border-linha ml-auto flex flex-wrap items-center gap-2 border-l pl-3">
          <select
            value={destino}
            onChange={(e) => setDestino(e.target.value)}
            className="entrada w-auto"
            aria-label="Lista de destino"
            disabled={Boolean(nova.trim())}
          >
            <option value="">escolher lista…</option>
            {listas.map((lista) => (
              <option key={lista.id} value={lista.id}>
                {lista.name} ({lista.company_count})
              </option>
            ))}
          </select>
          <span className="text-legenda text-tinta-fraca">ou</span>
          <input
            value={nova}
            onChange={(e) => setNova(e.target.value)}
            placeholder="nova lista"
            aria-label="Nome da nova lista"
            className="entrada w-36"
          />
          <Botao variante="secundaria" Icone={Bookmark} onClick={salvarEmLista} disabled={ocupado}>
            Salvar em lista
          </Botao>
          <Botao variante="primaria" Icone={Target} onClick={mandarParaOCrm} carregando={ocupado}>
            Adicionar ao CRM
          </Botao>
          <button
            onClick={aoConcluir}
            title="Limpar seleção"
            aria-label="Limpar seleção"
            className="text-tinta-fraca hover:text-tinta hover:bg-papel-fundo rounded-sm p-2 transition-colors"
          >
            <X size={15} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
