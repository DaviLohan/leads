"""O queryset da tabela de empresas — a consulta central do produto.

Uma empresa útil para vender é a junção de cinco tabelas: identidade, endereço, contato,
diagnóstico e a relação comercial da organização que está olhando. Montar isso linha a linha
seria N+1 numa tela que existe para ser varrida com o olho; por isso tudo aqui vira
`Subquery` ou `FilteredRelation`, e a contagem de consultas não cresce com o número de
empresas.

**Nada neste módulo importa `analysis`, `crm` ou `providers`** — a ordem de dependência do
CLAUDE.md proíbe. Os dados desses apps entram pelo nome da relação reversa que as FKs *deles*
criaram apontando para cá (`score`, `opportunities`, `scans`, `leads`). É acoplamento por
string resolvido pelo ORM, não por import: `companies` continua embaixo na ordem, e continua
funcionando se um desses apps não existisse.

O preço dessa escolha são os literais de status logo abaixo. Há teste em `analysis` — que
pode importar daqui — garantindo que eles não se desencontrem das enums.
"""

from __future__ import annotations

from django.db.models import F, FilteredRelation, OuterRef, Q, QuerySet, Subquery

from apps.companies.models import (
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanyWebsite,
)

#: `analysis.Opportunity.Status.OPEN`.
OPPORTUNITY_OPEN = "OPEN"

#: `analysis.WebsiteScan.Status` — site visitado que não respondeu como deveria.
#: `BLOCKED` fica fora de propósito: é o guard de SSRF tendo recusado a URL, evento de
#: segurança, e não "site com problema" para mostrar ao vendedor.
SCAN_BROKEN = ("UNREACHABLE", "ERROR")


def contato_principal(kind: str, ref: str = "pk") -> Subquery:
    """O contato principal de um tipo, ou `None`.

    Inválido não conta: telefone que a normalização já reprovou não pode aparecer na coluna
    que o vendedor vai discar.

    `ref` é o caminho até a empresa a partir do queryset externo — `pk` quando se lista
    empresa, `company_id` quando se lista lead. É o que permite a tela de Leads mostrar
    telefone sem duplicar estas subconsultas.
    """
    return Subquery(
        CompanyContact.objects.filter(company=OuterRef(ref), kind=kind)
        .exclude(verification_status=CompanyContact.VerificationStatus.INVALID)
        .order_by("-is_primary", "created_at")
        .values("value_normalized")[:1]
    )


def do_endereco(campo: str, ref: str = "pk") -> Subquery:
    """Um campo do endereço principal. `ref`: ver `contato_principal`."""
    return Subquery(
        CompanyAddress.objects.filter(company=OuterRef(ref))
        .order_by("-is_primary", "created_at")
        .values(campo)[:1]
    )


def company_table_queryset(organization=None) -> QuerySet[Company]:
    """Empresas com tudo que a tabela mostra, em consulta constante.

    `organization` traz as colunas do CRM (esta empresa já é meu lead? em que estágio?). Sem
    ela — geração de schema, uso interno — as colunas simplesmente não existem, e não uma
    versão "vazia" que o serializer teria de adivinhar.
    """
    queryset = (
        Company.objects.exclude(status=Company.Status.MERGED).annotate(
            phone=contato_principal(CompanyContact.Kind.PHONE),
            # WhatsApp é coluna própria, nunca deduzida de celular: marcar como confirmado o
            # que ninguém confirmou faria o vendedor abrir conversa com quem não tem o app.
            whatsapp=contato_principal(CompanyContact.Kind.WHATSAPP),
            email=contato_principal(CompanyContact.Kind.EMAIL),
            city_name=do_endereco("city__name"),
            uf=do_endereco("city__state__uf"),
            website=Subquery(
                CompanyWebsite.objects.filter(company=OuterRef("pk"))
                .order_by("-is_primary", "created_at")
                .values("url")[:1]
            ),
            category_name=Subquery(
                CompanyCategory.objects.filter(company=OuterRef("pk"))
                .order_by("-is_primary", "created_at")
                .values("category__name")[:1]
            ),
            score_value=F("score__value"),
        )
        # Oportunidade é multivalorada: sai por prefetch (duas consultas por página) em vez
        # de subquery. Filtrar por OPEN aqui exigiria a enum de `analysis`; quem separa é o
        # serializer, sobre o que já veio na memória.
        .prefetch_related("opportunities__type")
        # Maior oportunidade primeiro — é a ordem de trabalho de quem prospecta. `nulls_last`
        # porque empresa ainda não pontuada não pode encabeçar a fila.
        .order_by(F("score_value").desc(nulls_last=True), "name")
    )

    if organization is not None:
        queryset = queryset.annotate(
            # `Lead` tem constraint de unicidade (organização, empresa): o LEFT JOIN filtrado
            # devolve no máximo uma linha, então não multiplica a listagem.
            lead_da_org=FilteredRelation("leads", condition=Q(leads__organization=organization)),
            lead_id=F("lead_da_org__id"),
            lead_stage_code=F("lead_da_org__stage__code"),
            lead_stage_name=F("lead_da_org__stage__name"),
        )

    return queryset
