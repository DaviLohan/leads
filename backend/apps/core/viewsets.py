"""Base de viewsets com escopo de organização.

Este é o ponto único onde o isolamento de tenant é imposto na camada HTTP (ADR-0007).
Todo recurso que herda de `TenantModel` deve ser exposto por um `TenantViewSet`.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied


class TenantViewSet(viewsets.ModelViewSet):
    """Restringe o queryset à organização ativa e a carimba na criação.

    Objeto de outra organização simplesmente não existe para este usuário: o filtro no
    queryset faz o detalhe responder **404**, não 403 — 403 confirmaria que o objeto existe.
    """

    def get_organization(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            raise PermissionDenied("Nenhuma organização ativa para esta sessão.")
        return organization

    def get_queryset(self):
        return super().get_queryset().for_organization(self.get_organization())

    def perform_create(self, serializer):
        serializer.save(organization=self.get_organization())
