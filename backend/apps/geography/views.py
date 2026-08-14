"""API de geografia — somente leitura.

Estado e município são dado público do IBGE, iguais para todo mundo (ADR-0007): não passam
por `TenantViewSet` e não têm filtro por organização. São `ReadOnlyModelViewSet` porque a
única forma de escrever é o importador — ninguém cria município pela API.

Autenticação continua exigida: é o default do DRF (`IsAuthenticated` em settings), e não há
motivo para abrir uma listagem de 5.570 linhas ao anônimo.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework import viewsets

from apps.core.text import normalize_name
from apps.geography.models import City, State
from apps.geography.serializers import CitySerializer, StateSerializer


class StateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = State.objects.all()
    serializer_class = StateSerializer
    filterset_fields = ["uf", "region"]


class CityFilter(filters.FilterSet):
    """Filtros da tela do Radar: recorte por estado e busca por nome."""

    uf = filters.CharFilter(field_name="state__uf", lookup_expr="iexact")
    q = filters.CharFilter(method="_by_name", label="Nome (sem acento, sem caixa)")

    class Meta:
        model = City
        fields = ["state", "uf", "q"]

    def _by_name(self, queryset, name, value):
        # Normaliza a busca com a mesma função que gerou a coluna: "São", "sao" e "SAO"
        # precisam encontrar a mesma cidade. Comparar contra `name` com `icontains` erraria
        # em qualquer nome acentuado e ainda deixaria de usar o índice.
        return queryset.filter(normalized_name__contains=normalize_name(value))


class CityViewSet(viewsets.ReadOnlyModelViewSet):
    # `select_related` evita um SELECT por linha para preencher `uf` no serializer (N+1).
    queryset = City.objects.select_related("state")
    serializer_class = CitySerializer
    filterset_class = CityFilter
