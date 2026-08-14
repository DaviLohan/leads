"""API de empresas — por enquanto só o catálogo de categorias.

`Company` continua sem endpoint: a tela de Empresas lê o diagnóstico por
`/analysis/scores/`, e listar empresas cruas não serve a nenhuma tela existente.

Categoria é outra coisa: é catálogo que a interface **precisa** ler para montar o formulário
de busca. Fixá-la no código do frontend, que foi o que a Etapa 13 fez, quebrou de duas
maneiras — mandava slug onde a API espera UUID, e categoria nova no banco nunca apareceria
na tela.
"""

from __future__ import annotations

from rest_framework import viewsets

from apps.companies.models import Category
from apps.companies.serializers import CategorySerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo global (ADR-0007). Escrever é pelo admin ou pelo seed."""

    serializer_class = CategorySerializer
    filterset_fields = ["is_active", "parent"]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by("name")
