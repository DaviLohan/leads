"use client";

import { Bookmark, Download, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Casca } from "@/components/casca";
import { BarraDeLote } from "@/components/lote";
import { TabelaDeEmpresas } from "@/components/tabela";
import { useAviso } from "@/components/ui/aviso";
import { Botao } from "@/components/ui/botao";
import { CabecalhoDaPagina } from "@/components/ui/cabecalho";
import { Erro, EsqueletoDeTabela, Vazio } from "@/components/ui/superficie";
import { errorMessage } from "@/lib/auth";
import { empresasDaLista, listaPorId, removerDaLista } from "@/lib/recursos";
import type { Empresa, Lista } from "@/lib/tipos";

/** O conteúdo de uma lista: as mesmas colunas da tela Empresas, telefone inclusive. */
export default function DetalheDaLista() {
  const { id } = useParams<{ id: string }>();
  const avisar = useAviso();
  const [lista, setLista] = useState<Lista | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [selecionadas, setSelecionadas] = useState<Set<string>>(new Set());
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    return Promise.all([listaPorId(id), empresasDaLista(id)])
      .then(([l, e]) => {
        setLista(l);
        setEmpresas(e.results);
      })
      .catch((e) => setErro(errorMessage(e, "Não foi possível carregar a lista.")))
      .finally(() => setCarregando(false));
  }, [id]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function remover() {
    const quantas = selecionadas.size;
    try {
      await removerDaLista(id, [...selecionadas]);
      setSelecionadas(new Set());
      await carregar();
      avisar(`${quantas} removida(s) da lista`);
    } catch (e) {
      avisar(errorMessage(e, "Não foi possível remover da lista."), "erro");
    }
  }

  return (
    <Casca>
      <CabecalhoDaPagina
        voltar={{ href: "/listas", rotulo: "Listas" }}
        titulo={lista?.name ?? "Lista"}
        descricao={lista?.description || undefined}
        contador={lista ? `${lista.company_count} empresa(s)` : undefined}
        acao={
          <>
            {selecionadas.size > 0 && (
              <Botao variante="perigo" Icone={Trash2} onClick={remover}>
                Remover {selecionadas.size}
              </Botao>
            )}
            {empresas.length > 0 && (
              <a href={`/api/v1/crm/lists/${id}/export/`}>
                <Botao variante="secundaria" Icone={Download}>
                  Exportar CSV
                </Botao>
              </a>
            )}
          </>
        }
      />

      {erro && <Erro mensagem={erro} aoTentarNovamente={carregar} className="mb-4" />}

      {carregando ? (
        <EsqueletoDeTabela linhas={5} colunas={6} />
      ) : empresas.length === 0 ? (
        <Vazio
          titulo="Lista vazia."
          descricao="Selecione empresas na tela Empresas e salve o lote nesta lista."
          Icone={Bookmark}
          acao={
            <Link href="/empresas">
              <Botao variante="primaria">Selecionar empresas</Botao>
            </Link>
          }
        />
      ) : (
        <div className="space-y-4">
          <BarraDeLote
            selecionadas={[...selecionadas]}
            aoConcluir={() => {
              setSelecionadas(new Set());
              carregar();
            }}
          />
          <TabelaDeEmpresas
            empresas={empresas}
            selecao={{
              selecionadas,
              aoAlternar: (empresaId) =>
                setSelecionadas((atual) => {
                  const proximo = new Set(atual);
                  if (!proximo.delete(empresaId)) proximo.add(empresaId);
                  return proximo;
                }),
              aoAlternarPagina: (marcar) =>
                setSelecionadas(marcar ? new Set(empresas.map((e) => e.id)) : new Set()),
            }}
          />
        </div>
      )}
    </Casca>
  );
}
