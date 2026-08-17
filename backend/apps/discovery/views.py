"""API de descoberta.

Busca é dado da organização (ADR-0007), então tudo passa por `TenantViewSet` — o ponto
único onde o isolamento é imposto. Busca de outra organização responde **404**, não 403.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import MinRole
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.viewsets import TenantViewSet
from apps.discovery.models import JOB_TERMINAL, Search, SearchJob, SearchResult, SearchStatus
from apps.discovery.serializers import (
    CriteriaSerializer,
    SearchJobSerializer,
    SearchResultSerializer,
    SearchSerializer,
)
from apps.discovery.services import SearchPlanError, cancel_search, plan_search, resolve_cities
from apps.discovery.tasks import dispatch_search


class SearchViewSet(TenantViewSet):
    serializer_class = SearchSerializer
    # Criar busca gasta cota de fonte externa: não é ação de leitor.
    permission_classes = [MinRole.at_least(Role.SALES)]
    filterset_fields = ["status"]
    throttle_scope = "search_create"

    def get_queryset(self):
        return (
            Search.objects.annotate(
                # Sem estas duas, `progress` e `job_count` fariam uma consulta por linha da
                # listagem — N+1 clássico numa tela que a interface consulta em laço
                # enquanto a busca roda.
                job_count=models.Count("jobs", distinct=True),
                jobs_done=models.Count(
                    "jobs", filter=models.Q(jobs__status__in=JOB_TERMINAL), distinct=True
                ),
                # Somas dos contadores que cada job já grava. `Coalesce` porque busca sem job
                # traria `None`, e a tela mostraria vazio onde o certo é zero.
                found_count=Coalesce(models.Sum("jobs__found_count"), 0),
                new_count=Coalesce(models.Sum("jobs__new_count"), 0),
                duplicate_count=Coalesce(models.Sum("jobs__duplicate_count"), 0),
                review_count=Coalesce(models.Sum("jobs__review_count"), 0),
                error_count=Coalesce(models.Sum("jobs__error_count"), 0),
            )
            # `order_by` explícito: a anotação cria um GROUP BY, e com ele o Django passa a
            # considerar o queryset não-ordenado mesmo com `Meta.ordering` — o que torna a
            # paginação instável entre páginas.
            .order_by("-created_at").for_organization(self.get_organization())
        )

    def get_throttles(self):
        # O teto de 30/hora vale para criar, não para acompanhar o progresso: a tela precisa
        # consultar de segundo em segundo enquanto a busca roda.
        self.throttle_scope = "search_create" if self.action == "create" else None
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        criterios = CriteriaSerializer(data=request.data.get("criteria") or {})
        criterios.is_valid(raise_exception=True)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        busca = serializer.save(
            organization=self.get_organization(),
            created_by=request.user,
            criteria=criterios.validated_data,
        )

        # Planeja de imediato para que os critérios impossíveis (nenhum município, categoria
        # sem mapeamento, plano acima do teto) virem 400 na hora — e não uma busca criada
        # que nunca sai de "aguardando".
        try:
            plan_search(busca)
        except SearchPlanError as exc:
            busca.delete()
            return Response({"criteria": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        record_audit(
            action=AuditLog.Action.CREATE,
            object_type="discovery.Search",
            object_id=busca.pk,
            actor=request.user,
            organization=self.get_organization(),
            request=request,
            changes={"name": busca.name, "jobs": busca.jobs.count()},
        )

        dispatch_search.delay(str(busca.pk))

        # Relê pelo queryset anotado: o objeto recém-salvo não tem `job_count` nem
        # `jobs_done`, e a resposta do POST precisa ter o mesmo formato da listagem — senão
        # a interface tem dois contratos para o mesmo recurso.
        busca = self.get_queryset().get(pk=busca.pk)
        return Response(self.get_serializer(busca).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        """Quanto trabalho estes critérios dariam, sem criar nada nem tocar a rede.

        Existe para que o usuário veja "399 municípios" antes de disparar, em vez de
        descobrir depois que pediu uma varredura de sete horas.
        """
        criterios = CriteriaSerializer(data=request.data.get("criteria") or request.data)
        criterios.is_valid(raise_exception=True)

        cidades = resolve_cities(criterios.validated_data)
        return Response(
            {
                "cities": len(cidades),
                "categories": len(criterios.validated_data["category_ids"]),
                "providers": len(criterios.validated_data["provider_slugs"]),
                "estimated_jobs": len(cidades)
                * len(criterios.validated_data["category_ids"])
                * len(criterios.validated_data["provider_slugs"]),
                # O limite vai junto para que a tela possa impedir o envio sem saber o número
                # de cor: ele é variável de ambiente, e um 500 fixo no frontend viraria mentira
                # no primeiro deploy que o mudasse.
                "max_jobs": settings.DISCOVERY_MAX_JOBS_PER_SEARCH,
            }
        )

    @action(detail=True, methods=["get"])
    def jobs(self, request, pk=None):
        consulta = self.get_object().jobs.select_related("city__state", "category", "provider")
        pagina = self.paginate_queryset(consulta)
        return self.get_paginated_response(SearchJobSerializer(pagina, many=True).data)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        consulta = SearchResult.objects.filter(search_job__search=self.get_object()).select_related(
            "company"
        )
        if tipo := request.query_params.get("match_type"):
            consulta = consulta.filter(match_type=tipo)
        pagina = self.paginate_queryset(consulta)
        return self.get_paginated_response(SearchResultSerializer(pagina, many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        busca = self.get_object()
        if busca.status in (SearchStatus.COMPLETED, SearchStatus.CANCELLED):
            return Response(
                {"detail": "Esta busca já terminou."}, status=status.HTTP_400_BAD_REQUEST
            )

        cancelados = cancel_search(busca)
        record_audit(
            action=AuditLog.Action.UPDATE,
            object_type="discovery.Search",
            object_id=busca.pk,
            actor=request.user,
            organization=self.get_organization(),
            request=request,
            changes={"cancelled_jobs": cancelados},
        )
        return Response(self.get_serializer(busca).data)


class SearchJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Jobs soltos, para a tela de acompanhamento filtrar por situação."""

    serializer_class = SearchJobSerializer
    filterset_fields = ["status", "search"]

    def get_queryset(self):
        organizacao = getattr(self.request, "organization", None)
        return SearchJob.objects.select_related(
            "city__state", "category", "provider"
        ).for_organization(organizacao)
