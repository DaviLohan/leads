"""Autenticação — prioridade máxima do CLAUDE.md."""

from __future__ import annotations

import pytest
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import Role
from apps.core.models import AuditLog
from conftest import SENHA

pytestmark = pytest.mark.django_db


def test_login_com_credenciais_validas(api, user):
    response = api.post(
        "/api/v1/auth/login/", {"email": user.email, "password": SENHA}, format="json"
    )
    assert response.status_code == 200
    assert response.data["user"]["email"] == user.email
    assert "_auth_user_id" in api.session


def test_resposta_do_login_ja_traz_a_organizacao(api, user, org, make_member):
    """O middleware roda antes da view: sem re-resolver, a resposta sairia sem organização."""
    make_member(user, org, Role.OWNER)
    response = api.post(
        "/api/v1/auth/login/", {"email": user.email, "password": SENHA}, format="json"
    )
    assert response.data["organization"] is not None
    assert response.data["organization"]["slug"] == org.slug
    assert response.data["role"] == Role.OWNER


def test_login_aceita_email_com_maiusculas(api, user):
    response = api.post(
        "/api/v1/auth/login/", {"email": user.email.upper(), "password": SENHA}, format="json"
    )
    assert response.status_code == 200


def test_login_com_senha_errada(api, user):
    response = api.post(
        "/api/v1/auth/login/", {"email": user.email, "password": "errada"}, format="json"
    )
    assert response.status_code == 401
    assert "_auth_user_id" not in api.session


def test_login_de_usuario_inativo_e_recusado(api, make_user):
    inativo = make_user("inativo@exemplo.com", is_active=False)
    response = api.post(
        "/api/v1/auth/login/", {"email": inativo.email, "password": SENHA}, format="json"
    )
    assert response.status_code == 401


def test_mensagem_nao_distingue_email_inexistente_de_senha_errada(api, user):
    """Diferenciar as duas respostas entrega a lista de e-mails cadastrados."""
    senha_errada = api.post(
        "/api/v1/auth/login/", {"email": user.email, "password": "errada"}, format="json"
    )
    inexistente = api.post(
        "/api/v1/auth/login/", {"email": "ninguem@exemplo.com", "password": SENHA}, format="json"
    )
    assert senha_errada.status_code == inexistente.status_code == 401
    assert senha_errada.data == inexistente.data


def test_login_rotaciona_a_sessao(api, user):
    api.get("/api/v1/auth/csrf/")
    antes = api.session.session_key
    api.post("/api/v1/auth/login/", {"email": user.email, "password": SENHA}, format="json")
    assert api.session.session_key != antes


def test_login_gera_auditoria(api, user):
    api.post("/api/v1/auth/login/", {"email": user.email, "password": SENHA}, format="json")
    log = AuditLog.objects.filter(action=AuditLog.Action.LOGIN).first()
    assert log is not None
    assert log.actor_id == user.pk
    assert log.ip_address


def test_login_respeita_throttle(api, user, settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK}
    codigos = [
        api.post(
            "/api/v1/auth/login/", {"email": user.email, "password": "errada"}, format="json"
        ).status_code
        for _ in range(12)
    ]
    assert 429 in codigos, "endpoint de login precisa ser limitado por taxa"


def test_me_exige_autenticacao(api):
    assert api.get("/api/v1/auth/me/").status_code in (401, 403)


def test_me_devolve_organizacao_ativa(login_as, user, org, make_member):
    make_member(user, org, Role.MANAGER)
    api = login_as(user)
    data = api.get("/api/v1/auth/me/").data
    assert data["organization"]["slug"] == org.slug
    assert data["role"] == Role.MANAGER
    assert len(data["memberships"]) == 1


def test_usuario_sem_vinculo_nao_tem_organizacao(login_as, user):
    data = login_as(user).get("/api/v1/auth/me/").data
    assert data["organization"] is None
    assert data["role"] is None


def test_logout_encerra_a_sessao(login_as, user):
    api = login_as(user)
    assert api.post("/api/v1/auth/logout/").status_code == 204
    assert api.get("/api/v1/auth/me/").status_code in (401, 403)


def test_csrf_entrega_o_cookie(api):
    response = api.get("/api/v1/auth/csrf/")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies


class TestTrocaDeOrganizacao:
    def test_troca_para_organizacao_com_vinculo(self, login_as, user, make_org, make_member):
        a, b = make_org("Alfa"), make_org("Beta")
        make_member(user, a, Role.ADMIN)
        make_member(user, b, Role.VIEWER)
        api = login_as(user)

        response = api.post(
            "/api/v1/auth/organization/", {"organization_id": str(b.pk)}, format="json"
        )
        assert response.status_code == 200
        assert response.data["organization"]["slug"] == b.slug
        assert api.get("/api/v1/auth/me/").data["role"] == Role.VIEWER

    def test_recusa_organizacao_sem_vinculo(self, login_as, user, make_org, make_member):
        a, alheia = make_org("Alfa"), make_org("Alheia")
        make_member(user, a, Role.OWNER)
        api = login_as(user)

        response = api.post(
            "/api/v1/auth/organization/", {"organization_id": str(alheia.pk)}, format="json"
        )
        assert response.status_code == 404, "não deve confirmar que a organização existe"

    def test_vinculo_revogado_perde_acesso_na_requisicao_seguinte(
        self, login_as, user, org, make_member
    ):
        """Revogar acesso não pode depender de a sessão expirar."""
        membership = make_member(user, org, Role.ADMIN)
        api = login_as(user)
        assert api.get("/api/v1/auth/me/").data["organization"] is not None

        membership.is_active = False
        membership.save(update_fields=["is_active"])

        assert api.get("/api/v1/auth/me/").data["organization"] is None
        assert api.get("/api/v1/organizations/members/").status_code == 403


class TestSenha:
    def test_troca_exige_a_senha_atual(self, login_as, user):
        api = login_as(user)
        response = api.post(
            "/api/v1/auth/password/change/",
            {"current_password": "errada", "new_password": "outra-senha-forte-456"},
            format="json",
        )
        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password(SENHA)

    def test_troca_com_sucesso(self, login_as, user):
        api = login_as(user)
        response = api.post(
            "/api/v1/auth/password/change/",
            {"current_password": SENHA, "new_password": "outra-senha-forte-456"},
            format="json",
        )
        assert response.status_code == 204
        user.refresh_from_db()
        assert user.check_password("outra-senha-forte-456")

    def test_troca_recusa_senha_fraca(self, login_as, user):
        api = login_as(user)
        response = api.post(
            "/api/v1/auth/password/change/",
            {"current_password": SENHA, "new_password": "12345678"},
            format="json",
        )
        assert response.status_code == 400

    def test_troca_mantem_a_sessao_atual_e_derruba_as_outras(self, api, login_as, user):
        from rest_framework.test import APIClient

        outra = APIClient()
        outra.post("/api/v1/auth/login/", {"email": user.email, "password": SENHA}, format="json")

        atual = login_as(user)
        atual.post(
            "/api/v1/auth/password/change/",
            {"current_password": SENHA, "new_password": "outra-senha-forte-456"},
            format="json",
        )

        assert atual.get("/api/v1/auth/me/").status_code == 200
        assert outra.get("/api/v1/auth/me/").status_code in (401, 403)

    def test_reset_responde_204_para_email_desconhecido(self, api, user):
        """Resposta diferente para e-mail inexistente seria um oráculo de contas."""
        conhecido = api.post("/api/v1/auth/password/reset/", {"email": user.email}, format="json")
        desconhecido = api.post(
            "/api/v1/auth/password/reset/", {"email": "ninguem@exemplo.com"}, format="json"
        )
        assert conhecido.status_code == desconhecido.status_code == 204

    def test_reset_envia_email_e_nao_expoe_token_na_resposta(self, api, user):
        response = api.post("/api/v1/auth/password/reset/", {"email": user.email}, format="json")
        assert response.status_code == 204
        assert len(mail.outbox) == 1
        assert user.email in mail.outbox[0].to
        assert "uid=" in mail.outbox[0].body

    def test_reset_confirm_define_a_nova_senha(self, api, user):
        from django.contrib.auth.tokens import default_token_generator

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": token, "new_password": "nova-senha-forte-789"},
            format="json",
        )
        assert response.status_code == 204
        user.refresh_from_db()
        assert user.check_password("nova-senha-forte-789")

    def test_token_de_reset_e_de_uso_unico(self, api, user):
        from django.contrib.auth.tokens import default_token_generator

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        payload = {"uid": uid, "token": token, "new_password": "nova-senha-forte-789"}

        assert (
            api.post("/api/v1/auth/password/reset/confirm/", payload, format="json").status_code
            == 204
        )
        segunda = api.post("/api/v1/auth/password/reset/confirm/", payload, format="json")
        assert segunda.status_code == 400

    def test_token_de_reset_invalido_e_recusado(self, api, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": "token-forjado", "new_password": "nova-senha-forte-789"},
            format="json",
        )
        assert response.status_code == 400

    def test_uid_que_nao_e_uuid_nao_derruba_o_endpoint(self, api):
        """Base64 válido decodificando para não-UUID precisa dar 400, nunca 500.

        `filter(pk="abc")` levanta o `ValidationError` do Django — que não herda de
        `ValueError` nem é tratado pelo handler do DRF. O endpoint é `AllowAny`, então
        qualquer anônimo alcançaria o 500.
        """
        response = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {
                "uid": urlsafe_base64_encode(b"abc"),
                "token": "token-forjado",
                "new_password": "nova-senha-forte-789",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_uid_que_nao_e_base64_e_recusado(self, api):
        response = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {
                "uid": "@@@",
                "token": "token-forjado",
                "new_password": "nova-senha-forte-789",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_uid_invalido_responde_igual_a_token_invalido(self, api, user):
        """Mensagens distintas revelariam se o `uid` corresponde a alguém."""
        base = {"token": "token-forjado", "new_password": "nova-senha-forte-789"}
        real = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {**base, "uid": urlsafe_base64_encode(force_bytes(user.pk))},
            format="json",
        )
        malformado = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {**base, "uid": urlsafe_base64_encode(b"abc")},
            format="json",
        )
        assert real.status_code == malformado.status_code == 400
        assert real.json() == malformado.json()
