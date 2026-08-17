"""Listas de trabalho e ações em lote.

O que precisa ser verdade: salvar o mesmo lote duas vezes não duplica, lista de uma
organização não existe para a outra, e mandar 20 empresas para o funil respeita a supressão
uma a uma — um opt-out no meio do lote não pode passar por estar acompanhado.
"""

import pytest

from apps.companies.models import Company, CompanyContact
from apps.crm import services
from apps.crm.models import CompanyList, Lead

pytestmark = pytest.mark.django_db

URL = "/api/v1/crm/lists/"


@pytest.fixture
def empresas(db):
    return [Company.objects.create(name=f"Empresa {i}") for i in range(3)]


class TestListas:
    def test_cria_e_conta(self, api, login_as, vendedor, empresas):
        login_as(vendedor)

        criada = api.post(URL, {"name": "Dentistas Curitiba"}, format="json")
        assert criada.status_code == 201, criada.data

        lista_id = criada.data["id"]
        r = api.post(
            f"{URL}{lista_id}/items/",
            {"company_ids": [str(e.id) for e in empresas]},
            format="json",
        )
        assert r.status_code == 201
        assert r.data == {"adicionados": 3, "ja_estavam": 0}

        assert api.get(URL).data["results"][0]["company_count"] == 3

    def test_salvar_o_mesmo_lote_duas_vezes_nao_duplica(
        self, api, login_as, vendedor, empresas, org
    ):
        lista = CompanyList.objects.create(organization=org, name="Repetida")
        login_as(vendedor)
        ids = [str(e.id) for e in empresas]

        api.post(f"{URL}{lista.id}/items/", {"company_ids": ids}, format="json")
        segunda = api.post(f"{URL}{lista.id}/items/", {"company_ids": ids}, format="json")

        assert segunda.data == {"adicionados": 0, "ja_estavam": 3}
        assert lista.items.count() == 3

    def test_remove_do_lote(self, api, login_as, vendedor, empresas, org):
        lista = CompanyList.objects.create(organization=org, name="Para remover")
        login_as(vendedor)
        ids = [str(e.id) for e in empresas]
        api.post(f"{URL}{lista.id}/items/", {"company_ids": ids}, format="json")

        r = api.delete(f"{URL}{lista.id}/items/", {"company_ids": ids[:2]}, format="json")

        assert r.status_code == 200
        assert lista.items.count() == 1

    def test_lote_acima_do_teto_e_recusado(self, api, login_as, vendedor, org):
        import uuid

        lista = CompanyList.objects.create(organization=org, name="Gigante")
        login_as(vendedor)

        r = api.post(
            f"{URL}{lista.id}/items/",
            {"company_ids": [str(uuid.uuid4()) for _ in range(201)]},
            format="json",
        )
        assert r.status_code == 400

    def test_lista_de_outra_organizacao_responde_404(self, api, login_as, vendedor, make_org):
        outra = make_org("Concorrente")
        alheia = CompanyList.objects.create(organization=outra, name="Alheia")
        login_as(vendedor)

        assert api.get(f"{URL}{alheia.id}/").status_code == 404

    def test_empresas_da_lista_vem_com_telefone(self, api, login_as, vendedor, empresas, org):
        lista = CompanyList.objects.create(organization=org, name="Com contato")
        CompanyContact.objects.create(
            company=empresas[0],
            kind=CompanyContact.Kind.PHONE,
            value_raw="+554133330000",
            value_normalized="+554133330000",
            is_primary=True,
        )
        login_as(vendedor)
        api.post(f"{URL}{lista.id}/items/", {"company_ids": [str(empresas[0].id)]}, format="json")

        r = api.get(f"{URL}{lista.id}/companies/")

        assert r.status_code == 200
        assert r.data["results"][0]["phone"] == "+554133330000"


class TestLoteNoFunil:
    URL_BULK = "/api/v1/crm/leads/bulk/"

    def test_cria_varios_de_uma_vez(self, api, login_as, vendedor, funil, empresas):
        login_as(vendedor)

        r = api.post(self.URL_BULK, {"company_ids": [str(e.id) for e in empresas]}, format="json")

        assert r.status_code == 201, r.data
        assert r.data["criados"] == 3
        assert Lead.objects.count() == 3

    def test_quem_ja_estava_no_funil_nao_entra_duas_vezes(
        self, api, login_as, vendedor, funil, empresas, org
    ):
        services.create_lead(organization=org, company=empresas[0])
        login_as(vendedor)

        r = api.post(self.URL_BULK, {"company_ids": [str(e.id) for e in empresas]}, format="json")

        assert r.data == {"criados": 2, "ja_existiam": 1, "suprimidos": []}
        assert Lead.objects.count() == 3

    def test_supressao_morde_dentro_do_lote(
        self, api, login_as, admin, vendedor, funil, empresas, org
    ):
        """Um opt-out no meio de 20 não pode passar por estar acompanhado."""
        CompanyContact.objects.create(
            company=empresas[1],
            kind=CompanyContact.Kind.PHONE,
            value_raw="+554133330000",
            value_normalized="+554133330000",
        )
        services.suppress(
            organization=org,
            actor=admin,
            identifier_kind="PHONE",
            identifier_value="+554133330000",
            reason="pediu para não receber contato",
        )
        login_as(vendedor)

        r = api.post(self.URL_BULK, {"company_ids": [str(e.id) for e in empresas]}, format="json")

        assert r.data["criados"] == 2
        assert [s["name"] for s in r.data["suprimidos"]] == [empresas[1].name]
        assert not Lead.objects.filter(company=empresas[1]).exists()

    def test_leitor_nao_cria_lote(self, api, login_as, leitor, funil, empresas):
        login_as(leitor)

        r = api.post(self.URL_BULK, {"company_ids": [str(empresas[0].id)]}, format="json")
        assert r.status_code == 403


class TestPainel:
    URL_RESUMO = "/api/v1/crm/leads/summary/"

    def test_resume_a_prospeccao(self, api, login_as, vendedor, funil, empresas, org):
        services.create_lead(organization=org, company=empresas[0])
        login_as(vendedor)

        dados = api.get(self.URL_RESUMO).data

        assert dados["total"] == 1
        assert dados["novos_hoje"] == 1
        assert dados["sem_contato"] == 1
        # Nada decidido ainda: taxa é `None`, não zero. Zero diria "perdemos todas".
        assert dados["conversao"] is None
        assert {e["code"] for e in dados["por_estagio"]} >= {"novo", "ganho", "perdido"}

    def test_melhores_oportunidades_ignora_quem_ja_e_lead(
        self, api, login_as, vendedor, funil, empresas, org
    ):
        """O painel sugere quem abordar — não quem já está na fila."""
        services.create_lead(organization=org, company=empresas[0])
        login_as(vendedor)

        nomes = [e["name"] for e in api.get(self.URL_RESUMO).data["melhores_oportunidades"]]

        assert empresas[0].name not in nomes
        assert len(nomes) == 2

    def test_vendedor_le_o_funil(self, api, login_as, vendedor, funil):
        """Era MANAGER, e por isso a tela de Leads não abria para quem vende."""
        login_as(vendedor)
        assert api.get("/api/v1/crm/pipelines/").status_code == 200

    def test_vendedor_nao_altera_o_funil(self, api, login_as, vendedor, funil):
        login_as(vendedor)
        assert (
            api.post("/api/v1/crm/pipelines/", {"name": "Outro"}, format="json").status_code == 403
        )
