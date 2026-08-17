"""A API de busca, com o isolamento de tenant que ela obriga.

Busca é dado comercial: o que uma organização procurou não é da conta das outras. O teste
de vazamento é obrigatório (CLAUDE.md) e responde **404**, não 403 — 403 confirmaria que o
objeto existe.
"""

import pytest
from django.conf import settings

from apps.accounts.models import Role
from apps.core.models import AuditLog
from apps.discovery.models import JobStatus, Search, SearchStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def vendedor(make_user, make_member, org):
    user = make_user("vendedor@exemplo.com")
    make_member(user, org, role=Role.SALES)
    return user


@pytest.fixture
def leitor(make_user, make_member, org):
    user = make_user("leitor@exemplo.com")
    make_member(user, org, role=Role.VIEWER)
    return user


@pytest.fixture
def payload(londrina, dentistas, fonte):
    return {
        "name": "Dentistas em Londrina",
        "criteria": {
            "city_ids": [str(londrina.id)],
            "category_ids": [str(dentistas.id)],
            "provider_slugs": [fonte.slug],
        },
    }


class TestCriacao:
    def test_cria_planeja_e_dispara(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        resposta = api.post("/api/v1/discovery/searches/", payload, format="json")

        assert resposta.status_code == 201, resposta.data
        assert resposta.data["job_count"] == 1

        busca = Search.objects.get(pk=resposta.data["id"])
        # As tasks rodam síncronas no teste, então a busca já terminou.
        assert busca.status == SearchStatus.COMPLETED
        assert busca.progress == 100

    def test_organizacao_vem_da_sessao_e_nunca_do_payload(
        self, api, login_as, vendedor, payload, make_org, org
    ):
        """Aceitar organização do corpo seria escalonamento de privilégio (CLAUDE.md)."""
        outra = make_org("Concorrente")
        login_as(vendedor)

        resposta = api.post(
            "/api/v1/discovery/searches/", {**payload, "organization": str(outra.id)}, format="json"
        )

        assert resposta.status_code == 201
        assert Search.objects.get(pk=resposta.data["id"]).organization == org

    def test_leitor_nao_cria(self, api, login_as, leitor, payload):
        """Criar busca gasta cota de fonte externa — não é ação de leitor."""
        login_as(leitor)
        assert api.post("/api/v1/discovery/searches/", payload, format="json").status_code == 403

    def test_anonimo_nao_acessa(self, api):
        assert api.get("/api/v1/discovery/searches/").status_code == 403

    def test_criterios_invalidos_nao_deixam_busca_orfa(
        self, api, login_as, vendedor, payload, sem_mapeamento
    ):
        """Plano impossível vira 400 na hora, e não busca eternamente "aguardando"."""
        login_as(vendedor)
        payload["criteria"]["category_ids"] = [str(sem_mapeamento.id)]

        resposta = api.post("/api/v1/discovery/searches/", payload, format="json")

        assert resposta.status_code == 400
        assert "mapeamento" in str(resposta.data["criteria"])
        assert Search.objects.count() == 0

    def test_exige_estado_ou_municipio(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        payload["criteria"].pop("city_ids")

        resposta = api.post("/api/v1/discovery/searches/", payload, format="json")
        assert resposta.status_code == 400

    def test_grava_auditoria(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        api.post("/api/v1/discovery/searches/", payload, format="json")

        registro = AuditLog.objects.get(object_type="discovery.Search")
        assert registro.actor == vendedor
        assert registro.changes["jobs"] == 1


class TestPreview:
    def test_estima_sem_criar_nada(
        self, api, login_as, vendedor, londrina, maringa, dentistas, fonte
    ):
        """Ver "399 municípios" antes de disparar evita pedir uma varredura de sete horas."""
        login_as(vendedor)
        resposta = api.post(
            "/api/v1/discovery/searches/preview/",
            {
                "criteria": {
                    "uf": ["PR"],
                    "category_ids": [str(dentistas.id)],
                    "provider_slugs": [fonte.slug],
                }
            },
            format="json",
        )

        assert resposta.status_code == 200
        assert resposta.data == {
            "cities": 2,
            "categories": 1,
            "providers": 1,
            "estimated_jobs": 2,
            # O limite vem junto para a tela poder impedir o envio sem saber o número de cor:
            # ele é variável de ambiente, e um 500 fixo no frontend viraria mentira no
            # primeiro deploy que o mudasse.
            "max_jobs": settings.DISCOVERY_MAX_JOBS_PER_SEARCH,
        }
        assert Search.objects.count() == 0


class TestAcompanhamento:
    def test_lista_os_jobs_com_a_cidade(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        busca_id = api.post("/api/v1/discovery/searches/", payload, format="json").data["id"]

        resposta = api.get(f"/api/v1/discovery/searches/{busca_id}/jobs/")

        assert resposta.status_code == 200
        job = resposta.data["results"][0]
        assert (job["city"], job["uf"], job["status"]) == ("Londrina", "PR", JobStatus.COMPLETED)
        assert job["new_count"] == 4

    def test_lista_os_resultados(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        busca_id = api.post("/api/v1/discovery/searches/", payload, format="json").data["id"]

        resposta = api.get(f"/api/v1/discovery/searches/{busca_id}/results/")

        assert resposta.data["count"] == 4
        assert resposta.data["results"][0]["company_name"]

    def test_filtra_resultados_por_tipo(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        busca_id = api.post("/api/v1/discovery/searches/", payload, format="json").data["id"]

        resposta = api.get(
            f"/api/v1/discovery/searches/{busca_id}/results/", {"match_type": "POSSIBLE"}
        )
        assert resposta.data["count"] == 0


class TestIsolamentoEntreOrganizacoes:
    def test_busca_de_outra_organizacao_responde_404(
        self, api, login_as, vendedor, make_org, criar_busca
    ):
        """404, não 403: 403 confirmaria que o objeto existe."""
        outra = make_org("Concorrente")
        alheia = Search.objects.create(organization=outra, name="Segredo deles", criteria={})

        login_as(vendedor)
        assert api.get(f"/api/v1/discovery/searches/{alheia.id}/").status_code == 404

    def test_listagem_nao_mostra_a_dos_outros(self, api, login_as, vendedor, make_org, payload):
        outra = make_org("Concorrente")
        Search.objects.create(organization=outra, name="Segredo deles", criteria={})

        login_as(vendedor)
        api.post("/api/v1/discovery/searches/", payload, format="json")

        resposta = api.get("/api/v1/discovery/searches/")
        assert resposta.data["count"] == 1
        assert resposta.data["results"][0]["name"] == "Dentistas em Londrina"

    def test_jobs_de_outra_organizacao_nao_aparecem(
        self, api, login_as, vendedor, make_org, londrina, dentistas, fonte
    ):
        from apps.discovery.services import plan_search

        outra = make_org("Concorrente")
        alheia = Search.objects.create(
            organization=outra,
            name="Deles",
            criteria={
                "city_ids": [str(londrina.id)],
                "category_ids": [str(dentistas.id)],
                "provider_slugs": [fonte.slug],
            },
        )
        plan_search(alheia)

        login_as(vendedor)
        assert api.get("/api/v1/discovery/jobs/").data["count"] == 0


class TestCancelamento:
    def test_cancela(self, api, login_as, vendedor, criar_busca):
        from apps.discovery.services import plan_search

        busca = criar_busca()
        plan_search(busca)
        login_as(vendedor)

        resposta = api.post(f"/api/v1/discovery/searches/{busca.id}/cancel/")

        assert resposta.status_code == 200
        assert resposta.data["status"] == SearchStatus.CANCELLED

    def test_recusa_cancelar_o_que_ja_terminou(self, api, login_as, vendedor, payload):
        login_as(vendedor)
        busca_id = api.post("/api/v1/discovery/searches/", payload, format="json").data["id"]

        resposta = api.post(f"/api/v1/discovery/searches/{busca_id}/cancel/")
        assert resposta.status_code == 400
