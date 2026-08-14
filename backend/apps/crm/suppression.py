"""Verificação de supressão (LGPD, PROJECT_PLAN §3.4).

## Onde a verificação morde, e por quê

O PROJECT_PLAN diz "verificada no pipeline de ingestão, antes de persistir e antes de
enfileirar contato". Há uma tensão real aí que precisa ser resolvida explicitamente:

`Company` é **global** (ADR-0007) e `SuppressionEntry` é **da organização**. Bloquear a
persistência da empresa porque a organização A pediu opt-out esconderia essa empresa da
organização B — que nunca pediu nada e tem direito ao mesmo dado público.

Resolução: a supressão bloqueia **o que é da organização**, que é onde ela realmente
significa alguma coisa:

1. **Criar lead** — sem lead não há prospecção, e é o lead que representa a intenção de
   abordar.
2. **Registrar contato** — nenhuma interação de contato entra num lead suprimido.

O dado público continua no banco, global, como sempre foi. O que a organização não pode
fazer é usá-lo para abordar. É a leitura que respeita a LGPD sem quebrar o ADR-0007.

## Por identificador, nunca por empresa

MEI e profissional liberal são pessoa física, e a mesma pessoa reaparece com outro
`company_id` na próxima busca ou por outro provider. Suprimir só por empresa deixaria o
telefone escapar na varredura seguinte — que é exatamente o caso que o §3.4 levanta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from apps.companies.models import Company, CompanyContact, CompanyWebsite
from apps.crm.models import SuppressionEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SuppressionHit:
    """O que bateu na lista. Guardado para a recusa poder ser explicada e auditada."""

    kind: str
    value: str
    reason: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.value}" + (f" ({self.reason})" if self.reason else "")


def identifiers_of(company: Company) -> list[tuple[str, str]]:
    """Todos os identificadores de uma empresa que podem estar suprimidos.

    Uma consulta por relação, não por linha: esta função roda antes de cada criação de lead.
    """
    identificadores: list[tuple[str, str]] = [(SuppressionEntry.Kind.COMPANY, str(company.pk))]

    if company.tax_id:
        identificadores.append((SuppressionEntry.Kind.TAX_ID, company.tax_id))

    for kind, valor in CompanyContact.objects.filter(company=company).values_list(
        "kind", "value_normalized"
    ):
        alvo = (
            SuppressionEntry.Kind.EMAIL
            if kind == CompanyContact.Kind.EMAIL
            else SuppressionEntry.Kind.PHONE
        )
        identificadores.append((alvo, valor))

    for dominio in CompanyWebsite.objects.filter(company=company).values_list("domain", flat=True):
        identificadores.append((SuppressionEntry.Kind.DOMAIN, dominio))

    return identificadores


def check(organization, company: Company) -> SuppressionHit | None:
    """Devolve o primeiro identificador suprimido, ou `None`.

    Uma consulta só, com os identificadores todos: verificar um a um seria N consultas no
    caminho quente de criação de lead.
    """
    if organization is None:
        return None

    identificadores = identifiers_of(company)
    if not identificadores:
        return None

    from django.db.models import Q

    filtro = Q()
    for kind, valor in identificadores:
        filtro |= Q(identifier_kind=kind, identifier_value=valor)

    entrada = SuppressionEntry.objects.filter(organization=organization).filter(filtro).first()
    if entrada is None:
        return None

    return SuppressionHit(
        kind=entrada.identifier_kind, value=entrada.identifier_value, reason=entrada.reason
    )


def is_suppressed(organization, company: Company) -> bool:
    return check(organization, company) is not None
