"""API de empresas.

`Company` é dado público e **global** (ADR-0007): não passa por `TenantViewSet` e não é
filtrada por organização. O que é do tenant são as colunas do CRM (`lead_id`,
`lead_stage_code`), que entram como anotação da organização da sessão — ver
`companies/queries.py`. Uma organização nunca enxerga o lead da outra sobre a mesma empresa.

Somente leitura: quem escreve empresa é o pipeline de ingestão (ADR-0003).
"""

from __future__ import annotations

from django.http import StreamingHttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter

from apps.companies.export import linhas_csv
from apps.companies.filters import CompanyFilter
from apps.companies.models import Category
from apps.companies.queries import company_table_queryset
from apps.companies.serializers import (
    CategorySerializer,
    CompanyDetailSerializer,
    CompanyTableSerializer,
)
from apps.core.audit import record_audit
from apps.core.models import AuditLog


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo global (ADR-0007). Escrever é pelo admin ou pelo seed."""

    serializer_class = CategorySerializer
    filterset_fields = ["is_active", "parent"]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by("name")


class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    """A tela Empresas: filtrar a base e ver quem vale a ligação."""

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = CompanyFilter
    # Sem `ordering` padrão aqui de propósito: a ordem base (score desc, nulos por último)
    # vem do queryset, e o `OrderingFilter` só entra quando a tela pede outra.
    ordering_fields = ["score_value", "name", "discovered_at"]

    def get_serializer_class(self):
        return CompanyDetailSerializer if self.action == "retrieve" else CompanyTableSerializer

    def get_queryset(self):
        queryset = company_table_queryset(getattr(self.request, "organization", None))
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                "contacts", "addresses__city__state", "websites", "social_profiles", "categories"
            )
        return queryset

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Baixa o recorte atual em CSV.

        Mesmo filtro da tela: o que se vê é o que sai. Fica sob escopo de throttle próprio e
        grava auditoria — exportar carteira comercial é a ação que mais precisa de rastro, e
        é a primeira que se procura quando alguém pergunta "quem tirou esta lista daqui?".
        """
        queryset = self.filter_queryset(self.get_queryset())

        record_audit(
            action=AuditLog.Action.EXPORT,
            object_type="companies.Company",
            object_id=None,
            actor=request.user,
            organization=getattr(request, "organization", None),
            request=request,
            changes={"filtros": request.query_params.dict()},
        )

        resposta = StreamingHttpResponse(
            linhas_csv(queryset, CompanyTableSerializer), content_type="text/csv; charset=utf-8"
        )
        resposta["Content-Disposition"] = 'attachment; filename="empresas.csv"'
        return resposta

    def get_throttles(self):
        self.throttle_scope = "export" if self.action == "export" else None
        return super().get_throttles()
