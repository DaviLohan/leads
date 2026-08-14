"""Convites — único caminho para um usuário passar a existir (não há cadastro público)."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import Invitation, Membership, Role
from apps.accounts.services import InvitationError, accept_invitation
from conftest import SENHA

pytestmark = pytest.mark.django_db

NOVA_SENHA = "senha-de-convidado-456"


@pytest.fixture
def admin_api(login_as, make_user, org, make_member):
    admin = make_user("admin@exemplo.com")
    make_member(admin, org, Role.ADMIN)
    return login_as(admin)


def _convidar(api, email="convidado@exemplo.com", role=Role.SALES):
    return api.post(
        "/api/v1/organizations/invitations/", {"email": email, "role": role}, format="json"
    )


class TestCriacao:
    def test_admin_cria_convite_e_recebe_o_token_uma_vez(self, admin_api):
        response = _convidar(admin_api)
        assert response.status_code == 201
        assert response.data["token"]

        # A listagem nunca devolve o token.
        listagem = admin_api.get("/api/v1/organizations/invitations/")
        assert "token" not in listagem.data["results"][0]

    def test_banco_guarda_hash_e_nunca_o_token_cru(self, admin_api):
        token = _convidar(admin_api).data["token"]
        invitation = Invitation.objects.get()
        assert invitation.token_hash != token
        assert len(invitation.token_hash) == 64
        assert token not in str(invitation.__dict__)

    def test_papel_abaixo_de_admin_nao_convida(self, login_as, make_user, org, make_member):
        vendedor = make_user("vendas@exemplo.com")
        make_member(vendedor, org, Role.SALES)
        assert _convidar(login_as(vendedor)).status_code == 403

    def test_recusa_convite_para_quem_ja_e_membro(self, admin_api, make_user, org, make_member):
        membro = make_user("ja-membro@exemplo.com")
        make_member(membro, org, Role.VIEWER)
        response = _convidar(admin_api, email=membro.email)
        assert response.status_code == 400


class TestAceite:
    def test_aceite_cria_usuario_e_vinculo(self, admin_api, api, org):
        token = _convidar(admin_api).data["token"]

        response = api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": NOVA_SENHA, "full_name": "Pessoa Convidada"},
            format="json",
        )
        assert response.status_code == 204

        membership = Membership.objects.get(user__email="convidado@exemplo.com")
        assert membership.organization_id == org.pk
        assert membership.role == Role.SALES
        assert membership.user.check_password(NOVA_SENHA)

    def test_convidado_consegue_logar_depois(self, admin_api, api, org):
        token = _convidar(admin_api).data["token"]
        api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": NOVA_SENHA},
            format="json",
        )
        login = api.post(
            "/api/v1/auth/login/",
            {"email": "convidado@exemplo.com", "password": NOVA_SENHA},
            format="json",
        )
        assert login.status_code == 200
        assert login.data["organization"]["slug"] == org.slug

    def test_token_e_de_uso_unico(self, admin_api, api):
        token = _convidar(admin_api).data["token"]
        payload = {"token": token, "password": NOVA_SENHA}

        assert (
            api.post("/api/v1/auth/invitations/accept/", payload, format="json").status_code == 204
        )
        segunda = api.post("/api/v1/auth/invitations/accept/", payload, format="json")
        assert segunda.status_code == 400

    def test_token_expirado_e_recusado(self, admin_api, api):
        token = _convidar(admin_api).data["token"]
        Invitation.objects.update(expires_at=timezone.now() - timezone.timedelta(seconds=1))

        response = api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": NOVA_SENHA},
            format="json",
        )
        assert response.status_code == 400

    def test_token_revogado_e_recusado(self, admin_api, api):
        criado = _convidar(admin_api)
        token = criado.data["token"]
        admin_api.delete(f"/api/v1/organizations/invitations/{criado.data['id']}/")

        response = api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": NOVA_SENHA},
            format="json",
        )
        assert response.status_code == 400

    def test_token_forjado_e_recusado(self, api):
        response = api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": "nao-existe", "password": NOVA_SENHA},
            format="json",
        )
        assert response.status_code == 400

    def test_senha_fraca_e_recusada(self, admin_api, api):
        token = _convidar(admin_api).data["token"]
        response = api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": "12345678"},
            format="json",
        )
        assert response.status_code == 400

    def test_convite_para_usuario_existente_nao_troca_a_senha(self, admin_api, api, make_user, org):
        """Se trocasse, convidar o e-mail de alguém seria caminho de tomada de conta."""
        existente = make_user("existente@exemplo.com")
        token = _convidar(admin_api, email=existente.email).data["token"]

        api.post(
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": "senha-do-atacante-999"},
            format="json",
        )

        existente.refresh_from_db()
        assert existente.check_password(SENHA)
        assert not existente.check_password("senha-do-atacante-999")
        assert Membership.objects.filter(user=existente, organization=org).exists()


def test_servico_recusa_convite_de_organizacao_inativa(org, make_user):
    invitation, token = Invitation.issue(
        organization=org, email="alguem@exemplo.com", role=Role.VIEWER
    )
    org.is_active = False
    org.save(update_fields=["is_active"])

    with pytest.raises(InvitationError):
        accept_invitation(token=token, password=NOVA_SENHA)
