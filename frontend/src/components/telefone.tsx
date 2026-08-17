"use client";

import { Copy, MessageCircle } from "lucide-react";

import { useAviso } from "@/components/ui/aviso";

/**
 * Telefone: o dado comercial mais importante do produto.
 *
 * Fica visível na tabela, em mono e alinhado em coluna — é assim que se varre uma lista de
 * ligações com o olho. Copiar é um clique, e a confirmação vai para o aviso global: antes
 * ela aparecia dentro do próprio botão e sumia junto com ele.
 */

/**
 * `+554133330000` → `(41) 3333-0000`.
 *
 * Só aplica a máscara em número brasileiro reconhecido. Número de outro país e valor torto
 * saem como vieram: uma máscara errada é pior que nenhuma — faz o vendedor discar o que a
 * fonte não disse.
 */
export function formatarTelefone(e164: string): string {
  const digitos = e164.replace(/\D/g, "");
  const nacional =
    digitos.startsWith("55") && (digitos.length === 12 || digitos.length === 13)
      ? digitos.slice(2)
      : e164.startsWith("+")
        ? ""
        : digitos;

  if (nacional.length === 11) {
    return `(${nacional.slice(0, 2)}) ${nacional.slice(2, 7)}-${nacional.slice(7)}`;
  }
  if (nacional.length === 10) {
    return `(${nacional.slice(0, 2)}) ${nacional.slice(2, 6)}-${nacional.slice(6)}`;
  }
  return e164;
}

/** O link do WhatsApp. `null` quando não há número — nunca um link que não abre conversa. */
export function linkDeWhatsApp(numero: string | null): string | null {
  if (!numero) return null;
  const digitos = numero.replace(/\D/g, "");
  return digitos.length >= 10 ? `https://wa.me/${digitos}` : null;
}

/** Traço de ausência, igual em toda a interface. Nunca vazio: célula vazia parece bug. */
export function Ausente({ titulo = "Não informado pelas fontes" }: { titulo?: string }) {
  return (
    <span className="text-tinta-fraca/50" title={titulo} aria-label={titulo}>
      —
    </span>
  );
}

export function Telefone({ valor }: { valor: string | null }) {
  const avisar = useAviso();
  if (!valor) return <Ausente />;

  const formatado = formatarTelefone(valor);

  return (
    // `group/tel`: o botão de copiar só aparece no hover da célula, mas continua alcançável
    // pelo teclado (`focus-within` mantém a opacidade).
    <span className="group/tel inline-flex items-center gap-1 whitespace-nowrap">
      <a href={`tel:${valor}`} className="dados text-corpo text-tinta hover:text-acao">
        {formatado}
      </a>
      <button
        type="button"
        title="Copiar telefone"
        aria-label={`Copiar telefone ${formatado}`}
        onClick={async (evento) => {
          evento.preventDefault();
          evento.stopPropagation();
          await navigator.clipboard.writeText(valor);
          avisar("Telefone copiado");
        }}
        className="text-tinta-fraca hover:text-acao hover:bg-papel-fundo rounded-sm p-1 opacity-0 transition-all group-hover/tel:opacity-100 focus-visible:opacity-100"
      >
        <Copy size={13} aria-hidden />
      </button>
    </span>
  );
}

/**
 * O botão do WhatsApp.
 *
 * Só aparece quando existe contato do tipo WhatsApp: celular **não** é WhatsApp presumido.
 * Marcar como confirmado o que ninguém confirmou faria o vendedor abrir conversa com quem
 * não tem o aplicativo — e é a mesma regra do backend, onde o tipo é uma coluna própria.
 */
export function BotaoWhatsApp({ numero, rotulo }: { numero: string | null; rotulo?: string }) {
  const link = linkDeWhatsApp(numero);
  if (!link) return <Ausente titulo="Sem WhatsApp confirmado" />;

  return (
    <a
      href={link}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(evento) => evento.stopPropagation()}
      title="Abrir conversa no WhatsApp"
      className="text-ganho hover:bg-ganho-fraca text-apoio inline-flex items-center gap-1.5 rounded-sm px-1.5 py-1 font-medium whitespace-nowrap transition-colors"
    >
      <MessageCircle size={14} aria-hidden />
      {rotulo ?? "Abrir"}
    </a>
  );
}
