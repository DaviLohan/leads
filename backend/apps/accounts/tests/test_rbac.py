"""RBAC — matriz de papel por operação.

Autorização é sempre verificada no backend (SECURITY.md). Estes testes existem para que
uma mudança de papel não afrouxe permissão sem alguém perceber.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import ROLE_RANK, Membership, Role
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def como(login_as, make_user, org, make_member):
    """Autentica um usuário com o papel pedido na organização de teste."""

    def _como(role: str):
        user = make_user(f"{role.lower()}@exemplo.com")
        make_member(user, org, role)
        return login_as(user)

    return _como


def test_hierarquia_de_papeis_esta_ordenada():
    assert (
        ROLE_RANK[Role.VIEWER]
        < ROLE_RANK[Role.SALES]
        < ROLE_RANK[Role.MANAGER]
        < ROLE_RANK[Role.ADMIN]
        < ROLE_RANK[Role.OWNER]
    )


@pytest.mark.parametrize("role", [Role.VIEWER, Role.SALES, Role.MANAGER])
def test_abaixo_de_admin_nao_lista_membros(como, role):
    assert como(role).get("/api/v1/organizations/members/").status_code == 403


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OWNER])
def test_admin_e_owner_listam_membros(como, role):
    assert como(role).get("/api/v1/organizations/members/").status_code == 200


@pytest.mark.parametrize("role", [Role.VIEWER, Role.SALES, Role.MANAGER])
def test_abaixo_de_admin_nao_convida(como, role):
    response = como(role).post(
        "/api/v1/organizations/invitations/",
        {"email": "novo@exemplo.com", "role": Role.VIEWER},
        format="json",
    )
    assert response.status_code == 403


def test_sem_organizacao_ativa_nao_acessa_recurso_de_tenant(login_as, user):
    """Usuário autenticado, mas sem vínculo, não enxerga nada do produto."""
    assert login_as(user).get("/api/v1/organizations/members/").status_code == 403


def test_admin_altera_papel_de_membro(como, make_user, org, make_member):
    alvo = make_user("alvo@exemplo.com")
    membership = make_member(alvo, org, Role.VIEWER)

    response = como(Role.ADMIN).patch(
        f"/api/v1/organizations/members/{membership.pk}/", {"role": Role.MANAGER}, format="json"
    )
    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.role == Role.MANAGER


def test_mudanca_de_papel_gera_auditoria(como, make_user, org, make_member):
    alvo = make_user("alvo@exemplo.com")
    membership = make_member(alvo, org, Role.VIEWER)

    como(Role.ADMIN).patch(
        f"/api/v1/organizations/members/{membership.pk}/", {"role": Role.SALES}, format="json"
    )

    log = AuditLog.objects.filter(action=AuditLog.Action.PERMISSION_CHANGE).first()
    assert log is not None
    assert log.changes["role"] == [Role.VIEWER, Role.SALES]
    assert log.object_id == membership.pk


def test_remocao_de_membro_desativa_em_vez_de_apagar(como, make_user, org, make_member):
    alvo = make_user("alvo@exemplo.com")
    membership = make_member(alvo, org, Role.SALES)

    assert (
        como(Role.ADMIN).delete(f"/api/v1/organizations/members/{membership.pk}/").status_code
        == 204
    )

    membership.refresh_from_db()
    assert membership.is_active is False, "o histórico de quem fez o quê precisa sobreviver"


class TestUltimoProprietario:
    """A organização não pode ficar sem nenhum OWNER ativo."""

    def test_nao_rebaixa_o_unico_owner(self, login_as, make_user, org, make_member):
        owner = make_user("owner@exemplo.com")
        membership = make_member(owner, org, Role.OWNER)
        api = login_as(owner)

        response = api.patch(
            f"/api/v1/organizations/members/{membership.pk}/", {"role": Role.ADMIN}, format="json"
        )
        assert response.status_code == 400
        membership.refresh_from_db()
        assert membership.role == Role.OWNER

    def test_nao_remove_o_unico_owner(self, login_as, make_user, org, make_member):
        owner = make_user("owner@exemplo.com")
        membership = make_member(owner, org, Role.OWNER)

        response = login_as(owner).delete(f"/api/v1/organizations/members/{membership.pk}/")
        assert response.status_code == 400
        membership.refresh_from_db()
        assert membership.is_active is True

    def test_rebaixa_owner_quando_existe_outro(self, login_as, make_user, org, make_member):
        primeiro = make_user("owner1@exemplo.com")
        segundo = make_user("owner2@exemplo.com")
        make_member(primeiro, org, Role.OWNER)
        alvo = make_member(segundo, org, Role.OWNER)

        response = login_as(primeiro).patch(
            f"/api/v1/organizations/members/{alvo.pk}/", {"role": Role.ADMIN}, format="json"
        )
        assert response.status_code == 200
        alvo.refresh_from_db()
        assert alvo.role == Role.ADMIN


def test_papel_invalido_e_recusado(como, make_user, org, make_member):
    alvo = make_user("alvo@exemplo.com")
    membership = make_member(alvo, org, Role.VIEWER)

    response = como(Role.ADMIN).patch(
        f"/api/v1/organizations/members/{membership.pk}/", {"role": "SUPERGOD"}, format="json"
    )
    assert response.status_code == 400
    assert Membership.objects.get(pk=membership.pk).role == Role.VIEWER
