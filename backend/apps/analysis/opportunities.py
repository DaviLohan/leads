"""Opportunity Engine: transforma sinais observados em oportunidade de venda.

Junta as duas metades do ADR-0008: os predicados de `rules.py` (código, testável, revisado
em PR) e as linhas de `OpportunityType` (banco, ajustável sem deploy).

O que este módulo **não** faz: inventar sinal. Ele só lê o que o scanner observou. Empresa
nunca analisada não gera oportunidade nenhuma — "não sei" não pode virar "não tem", pela
mesma razão que `NOT_FOUND` tem o rótulo que tem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.analysis.models import Opportunity, OpportunityType, WebsiteScan
from apps.analysis.rules import CompanyContext, evaluate
from apps.companies.models import Company, CompanyContact

logger = logging.getLogger(__name__)


@dataclass
class DetectionReport:
    opened: int = 0
    kept: int = 0
    resolved: int = 0

    @property
    def total(self) -> int:
        return self.opened + self.kept + self.resolved


def build_context(company: Company) -> CompanyContext:
    """Monta o contexto que os predicados leem, com o mínimo de consultas.

    Contexto pronto, e não a empresa com seus relacionamentos: predicado que consulta o banco
    vira N+1 silencioso quando o motor roda sobre milhares de empresas.
    """
    ultima = WebsiteScan.objects.filter(company=company).order_by("-scanned_at").first()
    contatos = CompanyContact.objects.filter(company=company)

    # Três estados, e a diferença entre eles é o que separa "não sei" de "não tem":
    # `None` = nunca analisada; `False` = analisada e inalcançável; `True` = visitada.
    alcancavel = None if ultima is None else ultima.status == WebsiteScan.Status.OK

    # Os sinais só existem quando a visita deu certo. Tirados de um scan que falhou viriam
    # `False` pelo padrão do model — e "não observado" viraria "não tem", que é exatamente
    # o erro que faria o motor vender site para quem já tem.
    sinais = _sinais_observados(ultima) if ultima is not None and alcancavel else {}

    return CompanyContext(
        company_id=company.pk,
        name=company.name,
        website_status=company.website_status,
        has_website=company.websites.exists(),
        scan_status=ultima.status if ultima else None,
        site_reachable=alcancavel,
        **sinais,
        phone_count=contatos.filter(
            kind__in=(CompanyContact.Kind.PHONE, CompanyContact.Kind.WHATSAPP)
        ).count(),
        email_count=contatos.filter(kind=CompanyContact.Kind.EMAIL).count(),
        rating=float(company.rating) if company.rating is not None else None,
        review_count=company.review_count,
        category_slugs=frozenset(company.categories.values_list("slug", flat=True)),
    )


def _sinais_observados(scan: WebsiteScan) -> dict:
    """Os sinais de um scan bem-sucedido. Só é chamado quando a visita deu certo."""
    return {
        "is_https": scan.is_https,
        "has_viewport": scan.has_viewport,
        "has_contact_form": scan.has_contact_form,
        "has_whatsapp": scan.has_whatsapp,
        "has_booking": scan.has_booking,
        "has_cart": scan.has_cart,
        "response_time_ms": scan.response_time_ms,
    }


def detect(company: Company) -> DetectionReport:
    """Reavalia todos os tipos ativos para uma empresa.

    Idempotente: rodar de novo atualiza o que já existe em vez de empilhar duplicatas — a
    `UniqueConstraint(company, type)` arbitra.

    Oportunidade que deixou de valer não é apagada: vira `RESOLVED` com data. A clínica que
    finalmente pôs agendamento no ar sai do radar, mas o fato de já ter sido alvo continua
    valendo para quem for entender a conta.
    """
    contexto = build_context(company)
    relatorio = DetectionReport()

    tipos = list(OpportunityType.objects.filter(is_active=True))
    abertas = {
        o.type_id: o
        for o in Opportunity.objects.filter(company=company, status=Opportunity.Status.OPEN)
    }

    with transaction.atomic():
        for tipo in tipos:
            if not _vale_para_a_categoria(tipo, contexto):
                continue

            resultado = evaluate(tipo.rule_code, contexto, tipo.rule_params)
            if resultado is None:
                # Regra desconhecida ou com defeito: não abre nem fecha nada. Silêncio é o
                # comportamento certo — mexer no estado com base em regra quebrada é pior.
                continue

            existente = abertas.pop(tipo.id, None)

            if resultado:
                if existente is None:
                    Opportunity.objects.update_or_create(
                        company=company,
                        type=tipo,
                        defaults={
                            "status": Opportunity.Status.OPEN,
                            "confidence": tipo.base_confidence,
                            "evidence": _evidencia(tipo, contexto),
                            "resolved_at": None,
                        },
                    )
                    relatorio.opened += 1
                else:
                    existente.evidence = _evidencia(tipo, contexto)
                    existente.save(update_fields=["evidence", "updated_at"])
                    relatorio.kept += 1
            elif existente is not None:
                existente.status = Opportunity.Status.RESOLVED
                existente.resolved_at = timezone.now()
                existente.save(update_fields=["status", "resolved_at", "updated_at"])
                relatorio.resolved += 1

        # Sobrou aberta cujo tipo saiu do ar (desativado ou fora da categoria): resolve
        # também. Deixá-la aberta manteria no radar uma oportunidade que ninguém mais avalia.
        for orfa in abertas.values():
            orfa.status = Opportunity.Status.RESOLVED
            orfa.resolved_at = timezone.now()
            orfa.save(update_fields=["status", "resolved_at", "updated_at"])
            relatorio.resolved += 1

    return relatorio


def _vale_para_a_categoria(tipo: OpportunityType, ctx: CompanyContext) -> bool:
    """Lista vazia vale para qualquer categoria; preenchida, só para as listadas.

    É o que faz "sem agendamento" valer para clínica e não para oficina mecânica, sem um
    `if` de categoria dentro do motor.
    """
    if not tipo.category_slugs:
        return True
    return bool({s.lower() for s in tipo.category_slugs} & ctx.category_slugs)


def _evidencia(tipo: OpportunityType, ctx: CompanyContext) -> dict:
    """O que sustentava a conclusão no momento da deteção.

    Sem isto, "detectamos que não tem agendamento" é afirmação sem lastro — e quem for
    vender não tem o que dizer ao cliente.
    """
    return {
        "rule": tipo.rule_code,
        "params": tipo.rule_params,
        "website_status": ctx.website_status,
        "scan_status": ctx.scan_status,
        "site_reachable": ctx.site_reachable,
        "sinais": {
            "https": ctx.is_https,
            "responsivo": ctx.has_viewport,
            "formulario": ctx.has_contact_form,
            "whatsapp": ctx.has_whatsapp,
            "agendamento": ctx.has_booking,
            "carrinho": ctx.has_cart,
            "tempo_ms": ctx.response_time_ms,
        },
        "contatos": {"telefones": ctx.phone_count, "emails": ctx.email_count},
    }
