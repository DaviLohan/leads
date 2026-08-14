"""Configuração global do pytest.

Fixtures compartilhadas entram aqui à medida que os domínios nascem. O `MockProvider`
(Etapa 7) será registrado neste ponto para que nenhum teste dependa de rede.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

SENHA = "senha-forte-de-teste-123"


@pytest.fixture(autouse=True)
def _isola_o_cache():
    """Zera o cache entre testes.

    O throttling do DRF guarda o histórico de chamadas no cache. Sem isto, um teste que
    exercita o limite de taxa derruba os seguintes com 429 — e o motivo fica ilegível.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def user(db):
    from apps.accounts.models import User

    return User.objects.create_user(email="teste@exemplo.com", password=SENHA)


@pytest.fixture
def make_user(db):
    from apps.accounts.models import User

    def _make(email: str, **kwargs):
        return User.objects.create_user(email=email, password=SENHA, **kwargs)

    return _make


@pytest.fixture
def make_org(db):
    from apps.accounts.models import Organization

    def _make(name: str = "Organização Teste", **kwargs):
        return Organization.objects.create(name=name, **kwargs)

    return _make


@pytest.fixture
def make_member(db):
    from apps.accounts.models import Membership, Role

    def _make(user, organization, role=Role.VIEWER, **kwargs):
        return Membership.objects.create(user=user, organization=organization, role=role, **kwargs)

    return _make


@pytest.fixture
def org(make_org):
    return make_org("Formedica")


@pytest.fixture
def login_as(api):
    """Autentica de verdade pela API — exercita sessão e CSRF como o browser faria."""

    def _login(user, password: str = SENHA):
        response = api.post(
            "/api/v1/auth/login/", {"email": user.email, "password": password}, format="json"
        )
        assert response.status_code == 200, response.data
        return api

    return _login
