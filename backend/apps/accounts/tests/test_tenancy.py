"""Isolamento de tenant (ADR-0007).

Vazamento entre organizações é a falha mais grave que esta plataforma pode ter — um cliente
veria a prospecção do concorrente. Estes testes não podem ser removidos.

Regra verificada em toda parte: recurso de outra organização responde **404, não 403**.
403 confirmaria que o objeto existe.
"""

from __future__ import annotations

import pytest

from apps.accounts.middleware import SESSION_KEY
from apps.accounts.models import Invitation, Membership, Role
from apps.core.models import TenantQuerySet

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(make_org, make_user, make_member, login_as):
    """Duas organizações, cada uma com seu ADMIN. Sessão autenticada na Alfa."""
    alfa, beta = make_org("Alfa"), make_org("Beta")
    admin_alfa = make_user("admin-alfa@exemplo.com")
    admin_beta = make_user("admin-beta@exemplo.com")
    make_member(admin_alfa, alfa, Role.ADMIN)
    make_member(admin_beta, beta, Role.ADMIN)
    return {
        "alfa": alfa,
        "beta": beta,
        "admin_alfa": admin_alfa,
        "admin_beta": admin_beta,
        "api": login_as(admin_alfa),
    }


def test_listagem_de_membros_so_traz_a_organizacao_ativa(cenario):
    response = cenario["api"].get("/api/v1/organizations/members/")
    assert response.status_code == 200
    emails = {linha["user"]["email"] for linha in response.data["results"]}
    assert emails == {"admin-alfa@exemplo.com"}


def test_detalhe_de_membro_de_outra_organizacao_responde_404(cenario):
    alheio = Membership.objects.get(organization=cenario["beta"])
    response = cenario["api"].get(f"/api/v1/organizations/members/{alheio.pk}/")
    assert response.status_code == 404


def test_alteracao_de_membro_de_outra_organizacao_responde_404(cenario):
    alheio = Membership.objects.get(organization=cenario["beta"])
    response = cenario["api"].patch(
        f"/api/v1/organizations/members/{alheio.pk}/", {"role": Role.VIEWER}, format="json"
    )
    assert response.status_code == 404
    alheio.refresh_from_db()
    assert alheio.role == Role.ADMIN


def test_remocao_de_membro_de_outra_organizacao_responde_404(cenario):
    alheio = Membership.objects.get(organization=cenario["beta"])
    response = cenario["api"].delete(f"/api/v1/organizations/members/{alheio.pk}/")
    assert response.status_code == 404
    alheio.refresh_from_db()
    assert alheio.is_active is True


def test_convites_nao_vazam_entre_organizacoes(cenario):
    Invitation.issue(organization=cenario["beta"], email="alvo@exemplo.com", role=Role.VIEWER)
    Invitation.issue(organization=cenario["alfa"], email="meu@exemplo.com", role=Role.VIEWER)

    response = cenario["api"].get("/api/v1/organizations/invitations/")
    emails = {linha["email"] for linha in response.data["results"]}
    assert emails == {"meu@exemplo.com"}


def test_detalhe_de_convite_alheio_responde_404(cenario):
    alheio, _ = Invitation.issue(
        organization=cenario["beta"], email="alvo@exemplo.com", role=Role.VIEWER
    )
    response = cenario["api"].get(f"/api/v1/organizations/invitations/{alheio.pk}/")
    assert response.status_code == 404


def test_convite_nasce_na_organizacao_ativa_mesmo_se_o_cliente_mandar_outra(cenario):
    """A organização vem da sessão, nunca do payload."""
    response = cenario["api"].post(
        "/api/v1/organizations/invitations/",
        {
            "email": "novo@exemplo.com",
            "role": Role.VIEWER,
            "organization": str(cenario["beta"].pk),
        },
        format="json",
    )
    assert response.status_code == 201
    assert Invitation.objects.get(email="novo@exemplo.com").organization_id == cenario["alfa"].pk


def test_sessao_forjada_com_organizacao_alheia_e_ignorada(cenario):
    """Escrever direto na sessão não concede acesso: a membership é revalidada."""
    api = cenario["api"]
    sessao = api.session
    sessao[SESSION_KEY] = str(cenario["beta"].pk)
    sessao.save()

    data = api.get("/api/v1/auth/me/").data
    assert data["organization"]["slug"] == cenario["alfa"].slug


def test_usuario_em_duas_organizacoes_ve_apenas_a_ativa(cenario, make_user, make_member, login_as):
    ponte = make_user("ponte@exemplo.com")
    make_member(ponte, cenario["alfa"], Role.ADMIN)
    make_member(ponte, cenario["beta"], Role.ADMIN)
    api = login_as(ponte)

    api.post(
        "/api/v1/auth/organization/", {"organization_id": str(cenario["alfa"].pk)}, format="json"
    )
    emails_alfa = {
        linha["user"]["email"]
        for linha in api.get("/api/v1/organizations/members/").data["results"]
    }

    api.post(
        "/api/v1/auth/organization/", {"organization_id": str(cenario["beta"].pk)}, format="json"
    )
    emails_beta = {
        linha["user"]["email"]
        for linha in api.get("/api/v1/organizations/members/").data["results"]
    }

    assert "admin-alfa@exemplo.com" in emails_alfa
    assert "admin-alfa@exemplo.com" not in emails_beta
    assert "admin-beta@exemplo.com" in emails_beta


class TestTenantQuerySet:
    def test_filtra_pela_organizacao(self, cenario):
        assert Membership.objects.for_organization(cenario["alfa"]).count() == 1

    def test_organizacao_nula_nao_devolve_nada(self):
        """Falha fechada: sem organização resolvida, o queryset é vazio — nunca tudo."""
        assert Membership.objects.for_organization(None).count() == 0

    def test_esta_disponivel_nos_managers_de_tenant(self):
        assert isinstance(Membership.objects.all(), TenantQuerySet)
        assert isinstance(Invitation.objects.all(), TenantQuerySet)
