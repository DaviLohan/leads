"""Resolução da organização ativa da requisição.

`request.organization` é a base de todo o isolamento de tenant. Ele é resolvido a cada
requisição a partir da sessão e **revalidado contra a membership ativa** — assim revogar o
acesso de alguém tem efeito na requisição seguinte, sem esperar a sessão expirar.

A organização nunca vem de parâmetro enviado pelo cliente.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

SESSION_KEY = "active_organization_id"


class OrganizationMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.organization = None  # type: ignore[attr-defined]
        request.membership = None  # type: ignore[attr-defined]

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            membership = resolve_membership(request)
            if membership is not None:
                request.membership = membership  # type: ignore[attr-defined]
                request.organization = membership.organization  # type: ignore[attr-defined]

        return self.get_response(request)


def active_memberships(user):
    from apps.accounts.models import Membership

    return (
        Membership.objects.select_related("organization")
        .filter(user=user, is_active=True, organization__is_active=True)
        .order_by("organization__name")
    )


def resolve_membership(request: HttpRequest):
    """Membership correspondente à organização ativa da sessão.

    Sem escolha na sessão, e havendo uma única organização, ela é selecionada
    automaticamente — o caso comum de quem pertence a um time só.
    """
    memberships = active_memberships(request.user)
    chosen_id = request.session.get(SESSION_KEY)

    if chosen_id:
        membership = memberships.filter(organization_id=chosen_id).first()
        if membership is not None:
            return membership
        # A escolha deixou de ser válida (vínculo revogado, organização desativada).
        request.session.pop(SESSION_KEY, None)

    membership = memberships.first()
    if membership is not None and memberships.count() == 1:
        request.session[SESSION_KEY] = str(membership.organization_id)
        return membership
    return membership


def set_active_organization(request: HttpRequest, organization) -> None:
    request.session[SESSION_KEY] = str(organization.pk)
