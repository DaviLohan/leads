"""Fixtures do CRM.

Ficam aqui, e não em cada módulo de teste, porque papel de usuário e funil padrão são
pré-requisito de quase todo teste deste app — importar fixture de um módulo de teste para
outro funciona, mas o ruff acusa (F811) e a leitura fica pior.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.companies.models import Company
from apps.crm.management.commands.seed_pipeline import criar_funil_padrao


@pytest.fixture
def funil(org):
    return criar_funil_padrao(org)


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Clínica São José")


@pytest.fixture
def vendedor(make_user, make_member, org):
    u = make_user("vendedor@exemplo.com")
    make_member(u, org, role=Role.SALES)
    return u


@pytest.fixture
def admin(make_user, make_member, org):
    u = make_user("admin@exemplo.com")
    make_member(u, org, role=Role.ADMIN)
    return u


@pytest.fixture
def leitor(make_user, make_member, org):
    u = make_user("leitor@exemplo.com")
    make_member(u, org, role=Role.VIEWER)
    return u
