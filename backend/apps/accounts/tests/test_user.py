"""Usuário: e-mail como identidade e senha sempre hasheada (SECURITY.md)."""

from __future__ import annotations

import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_cria_usuario_com_email_normalizado():
    user = User.objects.create_user(email="Ana@Exemplo.COM.BR", password="senha-forte-123")
    assert user.email == "ana@exemplo.com.br"
    assert user.is_active
    assert not user.is_staff
    assert user.id.version == 7


def test_senha_nunca_e_armazenada_em_texto():
    user = User.objects.create_user(email="ana@exemplo.com", password="senha-forte-123")
    assert user.password != "senha-forte-123"
    assert user.check_password("senha-forte-123")
    assert not user.check_password("outra")


def test_email_e_unico():
    User.objects.create_user(email="ana@exemplo.com", password="senha-forte-123")
    with pytest.raises(Exception):  # noqa: B017 - IntegrityError depende do backend
        User.objects.create_user(email="ana@exemplo.com", password="outra-senha-123")


def test_email_vazio_e_recusado():
    with pytest.raises(ValueError, match="E-mail"):
        User.objects.create_user(email="", password="senha-forte-123")


def test_superusuario_tem_permissoes():
    user = User.objects.create_superuser(email="root@exemplo.com", password="senha-forte-123")
    assert user.is_staff
    assert user.is_superuser
