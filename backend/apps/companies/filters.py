"""Filtros da tela Empresas.

Todo filtro é do servidor: a tabela pagina, e filtrar no navegador só funcionaria enquanto a
base coubesse numa página — que é justamente o cenário que este produto não tem.

Onde o filtro atravessa uma relação multivalorada (endereço, contato, categoria) o corte é
por `Exists`, não por `JOIN`: empresa com dois endereços na mesma cidade apareceria duas
vezes na listagem, e `distinct()` sobre a tabela inteira é caro. Onde o dado mora em app
superior (`analysis`), o `Exists` exigiria import proibido, e aí sim é `JOIN` + `distinct`.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef
from django_filters import rest_framework as filters

from apps.companies.models import (
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanyWebsite,
)
from apps.companies.queries import OPPORTUNITY_OPEN, SCAN_BROKEN
from apps.core.text import normalize_name

SITE_CHOICES = [
    ("found", "Site identificado"),
    ("not_found", "Site não identificado nas fontes"),
    ("not_checked", "Ainda não verificado"),
    ("broken", "Site com problemas"),
]


def _tem_contato(queryset, kind: str, valor: bool):
    existe = Exists(
        CompanyContact.objects.filter(company=OuterRef("pk"), kind=kind).exclude(
            verification_status=CompanyContact.VerificationStatus.INVALID
        )
    )
    return queryset.filter(existe) if valor else queryset.exclude(existe)


class CompanyFilter(filters.FilterSet):
    q = filters.CharFilter(method="_por_nome", label="Nome")
    uf = filters.CharFilter(method="_por_uf", label="UF")
    # `field_name` aqui não filtra nada — quem filtra é o método. Ele existe para que o
    # gerador de schema saiba a que campo do model o parâmetro corresponde; sem isso o
    # drf-spectacular emite aviso e a checagem de deploy da CI falha.
    city = filters.BaseInFilter(
        field_name="addresses__city", method="_por_cidade", label="IDs de município"
    )
    category = filters.CharFilter(method="_por_categoria", label="Slugs de categoria")
    site = filters.ChoiceFilter(choices=SITE_CHOICES, method="_por_site")
    has_phone = filters.BooleanFilter(method="_tem_telefone")
    has_whatsapp = filters.BooleanFilter(method="_tem_whatsapp")
    has_email = filters.BooleanFilter(method="_tem_email")
    opportunity = filters.BaseInFilter(
        field_name="opportunities__type__code",
        method="_por_oportunidade",
        label="Códigos de oportunidade",
    )
    score_min = filters.NumberFilter(field_name="score__value", lookup_expr="gte")
    score_max = filters.NumberFilter(field_name="score__value", lookup_expr="lte")
    in_crm = filters.BooleanFilter(method="_no_crm", label="Já é lead desta organização")
    stage = filters.CharFilter(method="_por_estagio", label="Código do estágio no funil")

    class Meta:
        model = Company
        fields = ["status", "website_status"]

    def _por_nome(self, queryset, name, value):
        # Mesma normalização que gerou a coluna e o índice de trigrama: "São", "sao" e "SAO"
        # precisam achar a mesma empresa.
        return queryset.filter(normalized_name__contains=normalize_name(value))

    def _por_uf(self, queryset, name, value):
        return queryset.filter(
            Exists(
                CompanyAddress.objects.filter(company=OuterRef("pk"), city__state__uf__iexact=value)
            )
        )

    def _por_cidade(self, queryset, name, value):
        return queryset.filter(
            Exists(CompanyAddress.objects.filter(company=OuterRef("pk"), city_id__in=value))
        )

    def _por_categoria(self, queryset, name, value):
        slugs = [s for s in value.split(",") if s]
        return queryset.filter(
            Exists(CompanyCategory.objects.filter(company=OuterRef("pk"), category__slug__in=slugs))
        )

    def _por_site(self, queryset, name, value):
        if value == "found":
            return queryset.filter(website_status=Company.WebsiteStatus.FOUND)
        if value == "not_found":
            return queryset.filter(website_status=Company.WebsiteStatus.NOT_FOUND)
        if value == "not_checked":
            # Site nunca visitado: ou a fonte não trouxe endereço, ou trouxe e o scanner
            # ainda não passou. Os dois são "não sei", e "não sei" nunca vira "não tem".
            return queryset.filter(website_status=Company.WebsiteStatus.NOT_CHECKED).exclude(
                Exists(CompanyWebsite.objects.filter(company=OuterRef("pk")))
            )
        # `broken`: o site existe e a análise não conseguiu usá-lo. É o lead mais quente da
        # tela — a empresa acha que tem presença digital e não tem.
        return queryset.filter(scans__status__in=SCAN_BROKEN).distinct()

    def _tem_telefone(self, queryset, name, value):
        return _tem_contato(queryset, CompanyContact.Kind.PHONE, value)

    def _tem_whatsapp(self, queryset, name, value):
        return _tem_contato(queryset, CompanyContact.Kind.WHATSAPP, value)

    def _tem_email(self, queryset, name, value):
        return _tem_contato(queryset, CompanyContact.Kind.EMAIL, value)

    def _por_oportunidade(self, queryset, name, value):
        return queryset.filter(
            opportunities__type__code__in=value, opportunities__status=OPPORTUNITY_OPEN
        ).distinct()

    def _no_crm(self, queryset, name, value):
        # Corta pela anotação (`lead_id`), não pelo alias da `FilteredRelation`: `isnull`
        # sobre o alias não vira `IS NULL` no LEFT JOIN — devolve a tabela inteira em
        # silêncio, que foi exatamente o que o teste pegou.
        #
        # A anotação vem de `company_table_queryset` e só existe com organização na sessão.
        if "lead_id" not in queryset.query.annotations:
            return queryset
        return queryset.filter(lead_id__isnull=not value)

    def _por_estagio(self, queryset, name, value):
        if "lead_stage_code" not in queryset.query.annotations:
            return queryset
        return queryset.filter(lead_stage_code=value)
