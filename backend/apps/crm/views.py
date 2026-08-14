"""API do CRM.

Tudo aqui é do tenant (ADR-0007) e passa por `TenantViewSet`, o ponto único onde o
isolamento é imposto. Lead de outra organização responde **404**, não 403.
"""

from __future__ import annotations

from django.db import models
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import MinRole
from apps.companies.models import Company
from apps.core.viewsets import TenantViewSet
from apps.crm import services
from apps.crm.models import Lead, Note, Pipeline, PipelineStage, SuppressionEntry
from apps.crm.serializers import (
    InteractionSerializer,
    LeadSerializer,
    NoteSerializer,
    PipelineSerializer,
    SuppressionEntrySerializer,
)


class PipelineViewSet(TenantViewSet):
    serializer_class = PipelineSerializer
    permission_classes = [MinRole.at_least(Role.MANAGER)]

    def get_queryset(self):
        return (
            Pipeline.objects.prefetch_related(
                models.Prefetch(
                    "stages",
                    # `lead_count` por anotação: sem isso, a tela do funil faria uma consulta
                    # por coluna só para mostrar o número em cima de cada uma.
                    queryset=PipelineStage.objects.annotate(
                        lead_count=models.Count("leads")
                    ).order_by("position"),
                )
            )
            .for_organization(self.get_organization())
            .order_by("name")
        )


class LeadViewSet(TenantViewSet):
    serializer_class = LeadSerializer
    permission_classes = [MinRole.at_least(Role.SALES)]
    filterset_fields = ["stage", "owner", "stage__is_terminal"]

    def get_queryset(self):
        return (
            Lead.objects.select_related(
                "company", "company__score", "stage", "owner"
            ).for_organization(self.get_organization())
            # Maior score primeiro: é a ordem de trabalho de quem prospecta.
            .order_by("-score_snapshot", "-created_at")
        )

    def create(self, request, *args, **kwargs):
        """Cria o lead pelo serviço, e não pelo serializer.

        É o serviço que verifica supressão, escolhe o estágio inicial e abre o histórico.
        Deixar o serializer gravar direto puliria as três coisas.
        """
        empresa = Company.objects.filter(pk=request.data.get("company")).first()
        if empresa is None:
            raise ValidationError({"company": ["Empresa não encontrada."]})

        try:
            lead = services.create_lead(
                organization=self.get_organization(),
                company=empresa,
                owner=request.user,
                request=request,
            )
        except services.SuppressedError as exc:
            # 403 e não 400: não é payload inválido, é uma proibição.
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(lead)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        lead = self.get_object()
        estagio = PipelineStage.objects.filter(
            pk=request.data.get("stage"), pipeline__organization=self.get_organization()
        ).first()
        if estagio is None:
            raise ValidationError({"stage": ["Estágio não encontrado neste funil."]})

        services.move_lead(
            lead=lead,
            stage=estagio,
            actor=request.user,
            note=request.data.get("note", ""),
            request=request,
        )
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=["get", "post"])
    def interactions(self, request, pk=None):
        lead = self.get_object()

        if request.method == "GET":
            pagina = self.paginate_queryset(lead.interactions.select_related("author"))
            return self.get_paginated_response(InteractionSerializer(pagina, many=True).data)

        entrada = InteractionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            interacao = services.log_interaction(
                lead=lead, author=request.user, **entrada.validated_data
            )
        except services.SuppressedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(InteractionSerializer(interacao).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        lead = self.get_object()

        if request.method == "GET":
            pagina = self.paginate_queryset(lead.notes.select_related("author"))
            return self.get_paginated_response(NoteSerializer(pagina, many=True).data)

        entrada = NoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        nota = Note.objects.create(lead=lead, author=request.user, **entrada.validated_data)
        return Response(NoteSerializer(nota).data, status=status.HTTP_201_CREATED)


class SuppressionEntryViewSet(TenantViewSet):
    """Lista de quem não pode ser contatado (LGPD).

    Criar exige ADMIN: é decisão de conformidade, não de rotina comercial. E não tem
    `destroy` — remover alguém de uma lista de opt-out é o tipo de operação que precisa de
    decisão explícita e rastro, não de um botão de lixeira.
    """

    serializer_class = SuppressionEntrySerializer
    permission_classes = [MinRole.at_least(Role.ADMIN)]
    filterset_fields = ["identifier_kind"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return SuppressionEntry.objects.for_organization(self.get_organization()).order_by(
            "-created_at"
        )

    def create(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        registro, encerrados = services.suppress(
            organization=self.get_organization(),
            actor=request.user,
            **entrada.validated_data,
        )
        return Response(
            {**self.get_serializer(registro).data, "leads_encerrados": encerrados},
            status=status.HTTP_201_CREATED,
        )
