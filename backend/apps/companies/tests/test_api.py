"""A API de categorias.

Existe porque a tela de busca precisa do catálogo. Fixá-lo no frontend, que foi o que a
Etapa 13 fez, mandava slug onde a API espera UUID — e categoria nova nunca apareceria.
"""

import pytest

from apps.companies.models import Category

pytestmark = pytest.mark.django_db


@pytest.fixture
def categorias(db):
    Category.objects.create(slug="dentistas", name="Dentistas")
    Category.objects.create(slug="padarias", name="Padarias")
    Category.objects.create(slug="extinta", name="Extinta", is_active=False)


def test_anonimo_nao_lista(api, categorias):
    assert api.get("/api/v1/companies/categories/").status_code == 403


def test_lista_com_id_e_nome(api, login_as, user, categorias):
    login_as(user)
    resposta = api.get("/api/v1/companies/categories/")

    assert resposta.status_code == 200
    primeira = resposta.data["results"][0]
    # O `id` é o que a busca manda como `category_ids`; o `name` é o que a pessoa lê.
    assert set(primeira) >= {"id", "slug", "name"}


def test_categoria_inativa_nao_aparece(api, login_as, user, categorias):
    """Oferecer no formulário o que o planejamento vai recusar seria beco sem saída."""
    login_as(user)
    slugs = {c["slug"] for c in api.get("/api/v1/companies/categories/").data["results"]}

    assert slugs == {"dentistas", "padarias"}


def test_e_somente_leitura(api, login_as, user, categorias):
    login_as(user)
    resposta = api.post("/api/v1/companies/categories/", {"slug": "x", "name": "X"}, format="json")
    assert resposta.status_code == 405


def test_o_id_devolvido_serve_para_criar_busca(api, login_as, user, categorias, db):
    """O contrato que quebrou: o que a lista devolve tem de ser aceito pela busca."""
    from apps.discovery.serializers import CriteriaSerializer

    login_as(user)
    ids = [c["id"] for c in api.get("/api/v1/companies/categories/").data["results"]]

    entrada = CriteriaSerializer(
        data={"uf": ["PR"], "category_ids": ids, "provider_slugs": ["osm-overpass"]}
    )
    assert entrada.is_valid(), entrada.errors
