"""Registro de predicados (ADR-0008).

A divisão que o ADR trava: **o código diz como avaliar, o banco diz se vale, quanto e com
quais parâmetros.** Ajustar peso é `UPDATE`; criar tipo novo de regra é código — e isso é
deliberado, porque regra nova é lógica nova e lógica nova merece revisão em PR.

O caminho que este módulo existe para evitar: guardar a regra inteira no banco leva a um
mini-parser ou a `eval()`. Regra vira dado não testável, não versionado e sem revisão — e um
erro de digitação numa linha derruba o motor em produção.

Aqui não há `eval`, `exec` nem expressão vinda de string. Nunca.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompanyContext:
    """Tudo que um predicado pode olhar, já carregado.

    Contexto pronto, e não a empresa com seus relacionamentos: predicado que faz consulta
    vira N+1 silencioso quando o motor roda sobre milhares de empresas. Quem monta isto é
    `opportunities.build_context`, em uma consulta só.
    """

    company_id: Any
    name: str
    website_status: str
    has_website: bool
    # Da última análise. `None` quando a empresa nunca foi analisada — e "não sei" nunca
    # pode virar "não tem": é a mesma regra do `NOT_FOUND` (CLAUDE.md).
    scan_status: str | None = None
    is_https: bool | None = None
    has_viewport: bool | None = None
    has_contact_form: bool | None = None
    has_whatsapp: bool | None = None
    has_booking: bool | None = None
    has_cart: bool | None = None
    response_time_ms: int | None = None
    site_reachable: bool | None = None

    phone_count: int = 0
    email_count: int = 0
    rating: float | None = None
    review_count: int = 0
    category_slugs: frozenset[str] = field(default_factory=frozenset)


Predicate = Callable[[CompanyContext, dict], bool]

REGISTRO: dict[str, Predicate] = {}


def rule(code: str) -> Callable[[Predicate], Predicate]:
    """Registra um predicado sob um código. O banco referencia esse código."""

    def decorador(func: Predicate) -> Predicate:
        if code in REGISTRO:
            raise ValueError(f"Regra {code!r} registrada duas vezes.")
        REGISTRO[code] = func
        return func

    return decorador


def evaluate(code: str, ctx: CompanyContext, params: dict | None = None) -> bool | None:
    """Avalia um predicado. Devolve `None` quando não dá para afirmar.

    Código desconhecido não quebra o cálculo — só avisa (ADR-0008, regra 1). Um `UPDATE`
    errado no banco não pode derrubar o motor inteiro em produção.
    """
    predicado = REGISTRO.get(code)
    if predicado is None:
        logger.warning("Regra desconhecida, ignorada", extra={"code": code})
        return None

    try:
        return predicado(ctx, params or {})
    except Exception:
        # Um predicado com defeito derruba a sua regra, não a análise da empresa inteira.
        logger.exception("Regra falhou ao avaliar", extra={"code": code})
        return None


# --- Predicados -------------------------------------------------------------------------
#
# Todos devolvem `False` quando não há evidência. "Não sei" nunca vira "não tem": empresa
# nunca analisada não pode gerar oportunidade — venderíamos site para quem já tem.


@rule("sem_site")
def sem_site(ctx: CompanyContext, params: dict) -> bool:
    """Nenhum site identificado nas fontes analisadas.

    Exige que a análise tenha acontecido: enquanto `website_status` for `NOT_CHECKED`, a
    resposta honesta é "ainda não sei", não "não tem" (CLAUDE.md).
    """
    return not ctx.has_website and ctx.website_status == "NOT_FOUND"


@rule("site_fora_do_ar")
def site_fora_do_ar(ctx: CompanyContext, params: dict) -> bool:
    """Tem endereço identificado, mas ele não responde. Domínio expirado conta."""
    return ctx.has_website and ctx.site_reachable is False


@rule("site_sem_https")
def site_sem_https(ctx: CompanyContext, params: dict) -> bool:
    return ctx.site_reachable is True and ctx.is_https is False


@rule("site_nao_responsivo")
def site_nao_responsivo(ctx: CompanyContext, params: dict) -> bool:
    return ctx.site_reachable is True and ctx.has_viewport is False


@rule("site_lento")
def site_lento(ctx: CompanyContext, params: dict) -> bool:
    """`threshold_ms` vem do banco: o que é "lento" muda com o mercado, não com o código."""
    limite = int(params.get("threshold_ms", 3000))
    return ctx.response_time_ms is not None and ctx.response_time_ms > limite


@rule("sem_canal_de_contato")
def sem_canal_de_contato(ctx: CompanyContext, params: dict) -> bool:
    """Site no ar sem formulário nem WhatsApp: quem chega não consegue falar."""
    return ctx.site_reachable is True and not ctx.has_contact_form and not ctx.has_whatsapp


@rule("sem_agendamento")
def sem_agendamento(ctx: CompanyContext, params: dict) -> bool:
    return ctx.site_reachable is True and ctx.has_booking is False


@rule("sem_ecommerce")
def sem_ecommerce(ctx: CompanyContext, params: dict) -> bool:
    return ctx.site_reachable is True and ctx.has_cart is False


@rule("sem_whatsapp")
def sem_whatsapp(ctx: CompanyContext, params: dict) -> bool:
    """WhatsApp é o canal comercial padrão no Brasil; ausência é lacuna, não preferência."""
    return ctx.site_reachable is True and ctx.has_whatsapp is False


@rule("poucos_contatos")
def poucos_contatos(ctx: CompanyContext, params: dict) -> bool:
    return ctx.phone_count + ctx.email_count < int(params.get("minimo", 1))


@rule("da_categoria")
def da_categoria(ctx: CompanyContext, params: dict) -> bool:
    """Pertence a alguma das categorias em `slugs`.

    É o que permite "agendamento" valer para clínica e não para oficina, sem `if` de
    categoria espalhado pelo motor.
    """
    alvos = {s.lower() for s in params.get("slugs", [])}
    return bool(alvos & ctx.category_slugs)
