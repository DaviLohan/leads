import pytest

pytestmark = pytest.mark.django_db


def test_anonimo_nao_lista(api, base_importada):
    assert api.get("/api/v1/geography/states/").status_code == 403


def test_lista_estados(api, user, login_as, base_importada):
    login_as(user)
    resposta = api.get("/api/v1/geography/states/")

    assert resposta.status_code == 200
    assert resposta.data["count"] == 2
    assert {item["uf"] for item in resposta.data["results"]} == {"PR", "SP"}


def test_filtra_municipios_por_uf(api, user, login_as, base_importada):
    login_as(user)
    resposta = api.get("/api/v1/geography/cities/", {"uf": "pr"})

    assert resposta.status_code == 200
    assert resposta.data["count"] == 2
    assert all(item["uf"] == "PR" for item in resposta.data["results"])


def test_busca_por_nome_ignora_acento_e_caixa(api, user, login_as, base_importada):
    """Quem digita "sao paulo" tem de achar "São Paulo" — é o motivo de normalized_name."""
    login_as(user)

    for termo in ["São Paulo", "sao paulo", "SAO"]:
        resposta = api.get("/api/v1/geography/cities/", {"q": termo})
        assert resposta.status_code == 200, termo
        assert [item["name"] for item in resposta.data["results"]] == ["São Paulo"], termo


def test_lista_de_municipios_e_paginada(api, user, login_as, base_importada):
    login_as(user)
    resposta = api.get("/api/v1/geography/cities/", {"page_size": 2})

    assert resposta.data["count"] == 3
    assert len(resposta.data["results"]) == 2
    assert resposta.data["next"] is not None


def test_municipio_traz_a_uf_sem_consulta_extra(api, user, login_as, base_importada):
    """`select_related` no viewset: a lista não pode virar N+1 para preencher a UF."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login_as(user)
    with CaptureQueriesContext(connection) as consultas:
        resposta = api.get("/api/v1/geography/cities/")

    assert resposta.status_code == 200
    assert resposta.data["results"][0]["uf"]

    # Contar o total de consultas mediria também sessão e usuário, que nada têm a ver com
    # N+1. O que importa: uma única leitura de município, e ela já traz o estado no JOIN.
    leituras = [c["sql"] for c in consultas if "geography_city" in c["sql"]]
    pagina = [sql for sql in leituras if "COUNT(" not in sql]
    assert len(pagina) == 1, pagina
    assert "geography_state" in pagina[0]


def test_api_e_somente_leitura(api, user, login_as, base_importada):
    login_as(user)
    resposta = api.post(
        "/api/v1/geography/states/",
        {"ibge_code": "42", "uf": "SC", "name": "Santa Catarina", "region": "S"},
        format="json",
    )
    assert resposta.status_code == 405
