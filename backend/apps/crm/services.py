"""Regras do CRM: criar lead, registrar interação, mover no funil.

Tudo aqui roda em `transaction.atomic` e gera histórico. A regra que dá sentido ao módulo:
**mudança de estágio é evento, não campo.** Trocar `lead.stage` sem registrar a interação
apagaria a única evidência de que a decisão aconteceu, e quando.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.crm import suppression
from apps.crm.models import Interaction, Lead, Pipeline, PipelineStage

logger = logging.getLogger(__name__)


class SuppressedError(PermissionError):
    """A empresa está na lista de supressão desta organização (LGPD)."""


class CrmError(ValueError):
    """Operação de CRM que não pode acontecer."""


def default_pipeline(organization) -> Pipeline:
    """O funil padrão da organização, criado sob demanda.

    Criar aqui, e não exigir configuração prévia: a primeira pessoa que tenta prospectar não
    pode esbarrar em "configure um funil antes".
    """
    funil = Pipeline.objects.filter(organization=organization, is_default=True).first()
    if funil is not None:
        return funil

    from apps.crm.management.commands.seed_pipeline import criar_funil_padrao

    return criar_funil_padrao(organization)


@transaction.atomic
def create_lead(
    *,
    organization,
    company: Company,
    owner=None,
    stage: PipelineStage | None = None,
    request=None,
) -> Lead:
    """Cria o lead de uma empresa para uma organização.

    **É aqui que a supressão morde.** A empresa continua no banco, global e visível — o que
    a organização não pode é abordá-la. Ver `crm/suppression.py` para o porquê de a
    verificação não estar na persistência da empresa.

    Idempotente por constraint: a mesma empresa não vira dois leads na mesma organização,
    porque dois vendedores da mesma casa ligando para o mesmo cliente é o pior resultado.
    """
    if (bateu := suppression.check(organization, company)) is not None:
        logger.info(
            "Lead recusado por supressão",
            extra={"company": str(company.pk), "hit": str(bateu)},
        )
        raise SuppressedError(
            f"{company.name} está na lista de supressão desta organização ({bateu})."
        )

    if stage is None:
        funil = default_pipeline(organization)
        stage = funil.first_stage
        if stage is None:
            raise CrmError(f"O funil {funil.name!r} não tem nenhum estágio.")

    lead, criado = Lead.objects.get_or_create(
        organization=organization,
        company=company,
        defaults={
            "stage": stage,
            "owner": owner,
            # Retrato do score na entrada: o da empresa muda quando o site muda, a
            # prioridade com que este lead entrou na fila não.
            "score_snapshot": getattr(getattr(company, "score", None), "value", 0),
        },
    )

    if criado:
        Interaction.objects.create(
            lead=lead,
            author=owner,
            kind=Interaction.Kind.STATUS_CHANGE,
            description=f"Lead criado em {stage.name}.",
        )
        record_audit(
            action=AuditLog.Action.CREATE,
            object_type="crm.Lead",
            object_id=lead.pk,
            actor=owner,
            organization=organization,
            request=request,
            changes={"company": company.name, "stage": stage.code},
        )

    return lead


@transaction.atomic
def move_lead(
    *, lead: Lead, stage: PipelineStage, actor=None, note: str = "", request=None
) -> Lead:
    """Move o lead de estágio, registrando a mudança.

    A interação não é opcional: sem ela o funil vira um campo que muda sozinho, e ninguém
    consegue reconstruir por que um negócio foi perdido.
    """
    if stage.pipeline.organization_id != lead.organization_id:
        # Mover para o funil de outra organização vazaria o lead para fora do tenant.
        raise CrmError("O estágio pertence ao funil de outra organização.")

    if stage.pk == lead.stage_id:
        return lead

    anterior = lead.stage
    lead.stage = stage
    lead.save(update_fields=["stage", "updated_at"])

    Interaction.objects.create(
        lead=lead,
        author=actor,
        kind=Interaction.Kind.STATUS_CHANGE,
        description=note or f"{anterior.name} → {stage.name}",
    )
    record_audit(
        action=AuditLog.Action.UPDATE,
        object_type="crm.Lead",
        object_id=lead.pk,
        actor=actor,
        organization=lead.organization,
        request=request,
        changes={"de": anterior.code, "para": stage.code},
    )
    return lead


@transaction.atomic
def log_interaction(
    *,
    lead: Lead,
    kind: str,
    author=None,
    description: str = "",
    outcome: str = "",
    next_action: str = "",
    next_action_at=None,
    occurred_at=None,
) -> Interaction:
    """Registra um evento no histórico do lead.

    Contato com empresa suprimida é recusado mesmo com o lead já existindo: a supressão pode
    ter entrado depois, e é justamente aí que ela precisa valer.
    """
    if kind in Interaction.KINDS_DE_CONTATO and suppression.is_suppressed(
        lead.organization, lead.company
    ):
        raise SuppressedError(
            f"{lead.company.name} está na lista de supressão: contato não permitido."
        )

    interacao = Interaction.objects.create(
        lead=lead,
        author=author,
        kind=kind,
        description=description,
        outcome=outcome,
        next_action=next_action,
        next_action_at=next_action_at,
        occurred_at=occurred_at or timezone.now(),
    )

    campos = []
    # Só contato de verdade atualiza "último contato". Anotação interna e mudança de estágio
    # não são contato, e contá-los faria o time achar que falou com o cliente quando só mexeu
    # no sistema.
    if kind in Interaction.KINDS_DE_CONTATO:
        lead.last_contacted_at = interacao.occurred_at
        campos.append("last_contacted_at")
    if next_action_at:
        lead.next_action_at = next_action_at
        campos.append("next_action_at")

    if campos:
        lead.save(update_fields=[*campos, "updated_at"])

    return interacao


@transaction.atomic
def suppress(
    *, organization, identifier_kind: str, identifier_value: str, reason: str = "", actor=None
):
    """Registra um opt-out e encerra os leads afetados.

    Registrar sem encerrar deixaria o lead na fila de alguém, que ligaria amanhã. O opt-out
    tem de ter efeito imediato sobre o trabalho em andamento, não só sobre o futuro.
    """
    from apps.crm.models import SuppressionEntry

    entrada, _ = SuppressionEntry.objects.update_or_create(
        organization=organization,
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        defaults={"reason": reason, "created_by": actor},
    )

    encerrados = 0
    terminal = (
        PipelineStage.objects.filter(
            pipeline__organization=organization, is_terminal=True, is_won=False
        )
        .order_by("position")
        .last()
    )
    if terminal is not None:
        for lead in Lead.objects.filter(
            organization=organization, stage__is_terminal=False
        ).select_related("company", "stage"):
            if suppression.is_suppressed(organization, lead.company):
                move_lead(
                    lead=lead,
                    stage=terminal,
                    actor=actor,
                    note=f"Encerrado por supressão: {reason or identifier_value}",
                )
                encerrados += 1

    record_audit(
        action=AuditLog.Action.CONFIG_CHANGE,
        object_type="crm.SuppressionEntry",
        object_id=entrada.pk,
        actor=actor,
        organization=organization,
        changes={
            "kind": identifier_kind,
            "value": identifier_value,
            "leads_encerrados": encerrados,
        },
    )
    return entrada, encerrados
