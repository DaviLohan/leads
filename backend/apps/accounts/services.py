"""Regras de negócio de contas.

Fica fora das views (CLAUDE.md): tudo aqui é transacional e usado tanto pela API quanto
pelos comandos de gestão.
"""

from __future__ import annotations

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import Invitation, Membership, Organization, Role, User
from apps.core.audit import record_audit
from apps.core.models import AuditLog


class InvitationError(Exception):
    """Convite inexistente, expirado, revogado ou já utilizado."""


@transaction.atomic
def create_organization_with_owner(
    *,
    name: str,
    owner_email: str,
    owner_password: str,
    owner_full_name: str = "",
) -> tuple[Organization, User]:
    """Cria a organização e seu primeiro OWNER.

    Única porta de entrada inicial da plataforma — não existe cadastro público.
    """
    organization = Organization.objects.create(name=name)
    email = owner_email.lower().strip()
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            email=email, password=owner_password, full_name=owner_full_name
        )
    Membership.objects.create(user=user, organization=organization, role=Role.OWNER)
    return organization, user


@transaction.atomic
def accept_invitation(
    *,
    token: str,
    password: str,
    full_name: str = "",
    request: HttpRequest | None = None,
) -> User:
    """Consome o convite e garante o vínculo do usuário com a organização.

    O `select_for_update` fecha a corrida entre dois aceites simultâneos do mesmo token:
    quem chegar depois encontra `accepted_at` preenchido e é recusado.
    """
    invitation = Invitation.find_usable(token)
    if invitation is None:
        raise InvitationError("Convite inválido ou expirado.")

    invitation = (
        Invitation.objects.select_for_update().select_related("organization").get(pk=invitation.pk)
    )
    if not invitation.is_usable:
        raise InvitationError("Convite inválido ou expirado.")

    user = User.objects.filter(email=invitation.email).first()
    if user is None:
        user = User.objects.create_user(
            email=invitation.email, password=password, full_name=full_name
        )
    # Usuário que já existe NÃO tem a senha trocada pelo convite. Caso contrário, convidar o
    # e-mail de alguém e usar o próprio token seria um caminho de tomada de conta. Ele entra
    # com a senha que já tem; o convite só concede o vínculo.
    elif full_name and not user.full_name:
        user.full_name = full_name
        user.save(update_fields=["full_name", "updated_at"])

    membership, created = Membership.objects.get_or_create(
        user=user,
        organization=invitation.organization,
        defaults={"role": invitation.role},
    )
    if not created and not membership.is_active:
        membership.is_active = True
        membership.role = invitation.role
        membership.save(update_fields=["is_active", "role", "updated_at"])

    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])

    record_audit(
        action=AuditLog.Action.CREATE,
        object_type="Membership",
        object_id=membership.pk,
        actor=user,
        organization=invitation.organization,
        changes={"role": invitation.role, "via": "invitation"},
        request=request,
    )
    return user


@transaction.atomic
def change_member_role(
    *,
    membership: Membership,
    new_role: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Membership:
    """Altera o papel de um membro, registrando o antes e o depois na auditoria."""
    previous = membership.role
    if previous == new_role:
        return membership

    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])

    record_audit(
        action=AuditLog.Action.PERMISSION_CHANGE,
        object_type="Membership",
        object_id=membership.pk,
        actor=actor,
        organization=membership.organization,
        changes={"role": [previous, new_role]},
        request=request,
    )
    return membership
