"""API de análise.

Diagnóstico de site é dado público sobre a empresa (ADR-0007): `ReadOnlyModelViewSet` comum,
sem escopo de organização. Escrever só acontece pelo scanner.
"""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import MinRole
from apps.analysis.models import Opportunity, Score, WebsiteScan
from apps.analysis.serializers import (
    OpportunitySerializer,
    ScoreSerializer,
    WebsiteScanSerializer,
)
from apps.analysis.tasks import scan_company_task
from apps.companies.models import Company


class WebsiteScanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WebsiteScanSerializer
    filterset_fields = ["company", "status", "is_https", "has_booking"]

    def get_queryset(self):
        return WebsiteScan.objects.select_related("company").prefetch_related("findings")

    @action(detail=False, methods=["post"], url_path="companies/(?P<company_id>[^/.]+)")
    def rescan(self, request, company_id=None):
        """Reanalisa o site de uma empresa.

        Sai da rede para um endereço que o usuário influencia, então não é ação de leitor e
        respeita o escopo `analysis` de 60/hora, que existe no settings desde a fundação.
        """
        if not Company.objects.filter(pk=company_id).exists():
            return Response({"detail": "Empresa não encontrada."}, status=status.HTTP_404_NOT_FOUND)

        scan_company_task.delay(str(company_id))
        return Response({"detail": "Análise enfileirada."}, status=status.HTTP_202_ACCEPTED)

    def get_permissions(self):
        if self.action == "rescan":
            return [MinRole.at_least(Role.SALES)()]
        return super().get_permissions()

    def get_throttles(self):
        self.throttle_scope = "analysis" if self.action == "rescan" else None
        return super().get_throttles()


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    """Oportunidades detectadas. Somente leitura: quem escreve é o motor de regras.

    Global (ADR-0007): "esta clínica não tem agendamento" é fato sobre a empresa. O que é do
    tenant é o `Lead` que nasce daqui, na Etapa 12.
    """

    serializer_class = OpportunitySerializer
    filterset_fields = ["company", "status", "type__code"]

    def get_queryset(self):
        return (
            Opportunity.objects.select_related("company", "type")
            # Abertas primeiro e mais confiáveis no topo: é a ordem em que alguém trabalharia
            # a lista, e a paginação precisa de ordem explícita de qualquer forma.
            .order_by("status", "-confidence", "-detected_at")
        )


class ScoreViewSet(viewsets.ReadOnlyModelViewSet):
    """Pontuação dos leads, sempre com o breakdown. Escrever é do motor."""

    serializer_class = ScoreSerializer
    filterset_fields = ["company"]

    def get_queryset(self):
        # Maior pontuação primeiro: é a ordem de trabalho de quem prospecta.
        return (
            Score.objects.select_related("company")
            .prefetch_related("components")
            .order_by("-value", "company__name")
        )
