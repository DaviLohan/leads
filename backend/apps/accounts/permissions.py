"""RBAC.

Autorização é sempre verificada no backend (SECURITY.md). O frontend apenas esconde o que
o backend já nega.

Os cinco papéis são hierárquicos, então comparar posições resolve — sem tabela de permissão
por endpoint para manter em sincronia.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import ROLE_RANK, Role


class IsOrganizationMember(BasePermission):
    """Exige sessão autenticada com uma organização ativa."""

    message = "Nenhuma organização ativa para esta sessão."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "organization", None) is not None
        )


class MinRole(IsOrganizationMember):
    """Exige papel mínimo.

    Uso: `permission_classes = [MinRole.at_least(Role.ADMIN)]`.
    """

    minimum: str = Role.VIEWER
    message = "Seu papel nesta organização não permite esta operação."

    @classmethod
    def at_least(cls, role: str) -> type[MinRole]:
        return type(f"MinRole{role.title()}", (cls,), {"minimum": role})

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        return membership.rank >= ROLE_RANK[self.minimum]


class ReadOnlyOrMinRole(MinRole):
    """Leitura para qualquer membro; escrita a partir do papel mínimo.

    É o padrão dos recursos do produto: VIEWER enxerga tudo da organização e não altera nada.
    """

    minimum = Role.SALES

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return IsOrganizationMember.has_permission(self, request, view)
        return super().has_permission(request, view)
