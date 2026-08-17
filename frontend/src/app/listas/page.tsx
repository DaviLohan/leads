"use client";

import { Bookmark, ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { useAviso } from "@/components/ui/aviso";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Erro, Esqueleto, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import { criarLista, listarListas } from "@/lib/recursos";
import type { Lista } from "@/lib/tipos";

/**
 * Listas — o lote antes da decisão.
 *
 * Uma lista não prospecta ninguém: separa "as 20 clínicas de Curitiba sem site" para
 * trabalhar amanhã. Quem cria relação comercial é o funil, e a distinção é o que impede o
 * time de achar que salvou = abordou.
 */
export default function Listas() {
  const avisar = useAviso();
  const [listas, setListas] = useState<Lista[]>([]);
  const [nome, setNome] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    return listarListas()
      .then((p) => setListas(p.results))
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar as listas.")))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function criar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!nome.trim()) return;
    try {
      await criarLista(nome.trim());
      avisar(`Lista "${nome.trim()}" criada`);
      setNome("");
      setListas((await listarListas()).results);
    } catch (e) {
      avisar(errorMessage(e, "Não foi possível criar a lista."), "erro");
    }
  }

  return (
    <Casca>
      <CabecalhoDaPagina
        titulo="Listas"
        descricao="Recortes salvos da base. A mesma empresa pode estar em quantas listas fizerem sentido."
        contador={carregando ? undefined : `${listas.length}`}
        acao={
          <form onSubmit={criar} className="flex items-center gap-2">
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="nome da nova lista"
              aria-label="Nome da nova lista"
              className="entrada w-52"
            />
            <Botao type="submit" variante="primaria" Icone={Plus} disabled={!nome.trim()}>
              Criar
            </Botao>
          </form>
        }
      />

      {erro && <Erro mensagem={erro} aoTentarNovamente={carregar} className="mb-4" />}

      {carregando ? (
        <div className="border-linha bg-papel-alto divide-linha divide-y rounded-md border">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex h-16 items-center gap-4 px-4">
              <Esqueleto className="h-6 w-10" />
              <Esqueleto className="h-3 w-48" />
            </div>
          ))}
        </div>
      ) : listas.length === 0 ? (
        <Vazio
          titulo="Nenhuma lista ainda."
          descricao="Selecione empresas na tela Empresas e salve o lote aqui para trabalhar depois."
          Icone={Bookmark}
          acao={
            <Link href="/empresas">
              <Botao variante="primaria">Selecionar empresas</Botao>
            </Link>
          }
        />
      ) : (
        <ul className="border-linha bg-papel-alto divide-linha divide-y rounded-md border">
          {listas.map((lista) => (
            <li key={lista.id}>
              <Link
                href={`/listas/${lista.id}`}
                className="group hover:bg-papel/70 flex h-16 items-center gap-4 px-4 transition-colors"
              >
                {/* A contagem primeiro, em mono: é o que diz se a lista vale a sessão de hoje. */}
                <span className="dados text-tinta w-10 shrink-0 text-right text-lg font-semibold">
                  {lista.company_count}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-tinta block truncate font-medium">{lista.name}</span>
                  <span className="text-legenda text-tinta-fraca block truncate">
                    {lista.description || "sem descrição"} · atualizada em{" "}
                    {new Date(lista.updated_at).toLocaleDateString("pt-BR")}
                  </span>
                </span>
                <ChevronRight
                  size={16}
                  className="text-tinta-fraca group-hover:text-acao shrink-0 transition-colors"
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Casca>
  );
}
