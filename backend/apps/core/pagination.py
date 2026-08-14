"""Paginação padrão da API.

Regra do CLAUDE.md: toda listagem pagina. `max_page_size` existe para que o cliente não
consiga pedir a tabela inteira.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
