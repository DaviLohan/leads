"""A API de empresas — a tela central do produto.

O que estes testes protegem, em ordem de importância:

1. **telefone chega na listagem** — foi a ausência que motivou a reestruturação;
2. **"não sei" não vira "não tem"** em nenhum filtro;
3. **isolamento de tenant**: a empresa é global, mas "já é meu lead" é da organização;
4. **a consulta não cresce com o número de linhas** (o método da Etapa 14).
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.analysis.models import Opportunity, OpportunityType, Score, WebsiteScan
from apps.companies.models import (
    Category,
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanyWebsite,
)
from apps.crm import services
from apps.crm.management.commands.seed_pipeline import criar_funil_padrao
from apps.geography.models import City, State

pytestmark = pytest.mark.django_db

URL = "/api/v1/companies/"


@pytest.fixture
def parana(db):
    estado = State.objects.create(ibge_code="41", uf="PR", name="Paraná", region="S")
    return City.objects.create(state=estado, ibge_code="4106902", name="Curitiba")


@pytest.fixture
def acre(db):
    estado = State.objects.create(ibge_code="12", uf="AC", name="Acre", region="N")
    return City.objects.create(state=estado, ibge_code="1200401", name="Rio Branco")


@pytest.fixture
def dentistas(db):
    return Category.objects.create(slug="dentistas", name="Dentistas")


@pytest.fixture
def make_empresa(db):
    def _make(
        nome: str,
        *,
        cidade=None,
        categoria=None,
        telefone: str | None = None,
        whatsapp: str | None = None,
        site: str | None = None,
        website_status: str = Company.WebsiteStatus.NOT_CHECKED,
        score: int | None = None,
    ):
        empresa = Company.objects.create(name=nome, website_status=website_status)
        if cidade is not None:
            CompanyAddress.objects.create(company=empresa, city=cidade, is_primary=True)
        if categoria is not None:
            CompanyCategory.objects.create(company=empresa, category=categoria, is_primary=True)
        if telefone is not None:
            CompanyContact.objects.create(
                company=empresa,
                kind=CompanyContact.Kind.PHONE,
                value_raw=telefone,
                value_normalized=telefone,
                is_primary=True,
            )
        if whatsapp is not None:
            CompanyContact.objects.create(
                company=empresa,
                kind=CompanyContact.Kind.WHATSAPP,
                value_raw=whatsapp,
                value_normalized=whatsapp,
            )
        if site is not None:
            CompanyWebsite.objects.create(
                company=empresa, url=site, domain=site.split("//")[-1], is_primary=True
            )
        if score is not None:
            Score.objects.create(company=empresa, value=score, version="abc123")
        return empresa

    return _make


@pytest.fixture
def vendedor(make_user, make_member, org):
    u = make_user("vendedor@exemplo.com")
    make_member(u, org, role=Role.SALES)
    return u


class TestListagem:
    def test_anonimo_nao_lista(self, api):
        assert api.get(URL).status_code == 403

    def test_telefone_vem_na_linha(self, api, login_as, vendedor, make_empresa, parana, dentistas):
        """O dado que não existia em lugar nenhum da interface."""
        make_empresa(
            "Clínica Sorriso",
            cidade=parana,
            categoria=dentistas,
            telefone="+554133330000",
            whatsapp="+5541999990000",
            score=94,
        )
        login_as(vendedor)

        linha = api.get(URL).data["results"][0]

        assert linha["phone"] == "+554133330000"
        assert linha["whatsapp"] == "+5541999990000"
        assert linha["city"] == "Curitiba"
        assert linha["uf"] == "PR"
        assert linha["category"] == "Dentistas"
        assert linha["score"] == 94

    def test_empresa_sem_score_aparece(self, api, login_as, vendedor, make_empresa, parana):
        """A tela antiga listava pontuações: quem ainda não foi pontuado era invisível."""
        make_empresa("Recém-descoberta", cidade=parana)
        login_as(vendedor)

        r = api.get(URL)
        assert r.data["count"] == 1
        assert r.data["results"][0]["score"] is None

    def test_maior_score_primeiro_e_sem_score_por_ultimo(
        self, api, login_as, vendedor, make_empresa
    ):
        make_empresa("Sem pontuação")
        make_empresa("Alta", score=90)
        make_empresa("Baixa", score=10)
        login_as(vendedor)

        nomes = [c["name"] for c in api.get(URL).data["results"]]
        assert nomes == ["Alta", "Baixa", "Sem pontuação"]

    def test_empresa_fundida_nao_aparece(self, api, login_as, vendedor, make_empresa):
        sobrevivente = make_empresa("Sobrevivente")
        duplicata = make_empresa("Duplicata")
        duplicata.status = Company.Status.MERGED
        duplicata.merged_into = sobrevivente
        duplicata.save()
        login_as(vendedor)

        assert [c["name"] for c in api.get(URL).data["results"]] == ["Sobrevivente"]

    def test_oportunidades_abertas_na_linha(self, api, login_as, vendedor, make_empresa):
        empresa = make_empresa("Clínica")
        tipo = OpportunityType.objects.create(
            code="site-institucional", name="Site institucional", rule_code="sem_site"
        )
        resolvida = OpportunityType.objects.create(
            code="agendamento", name="Agendamento online", rule_code="sem_agendamento"
        )
        Opportunity.objects.create(company=empresa, type=tipo, status=Opportunity.Status.OPEN)
        Opportunity.objects.create(
            company=empresa, type=resolvida, status=Opportunity.Status.RESOLVED
        )
        login_as(vendedor)

        codigos = [o["code"] for o in api.get(URL).data["results"][0]["opportunities"]]
        assert codigos == ["site-institucional"]


class TestFiltros:
    def test_uf_e_cidade(self, api, login_as, vendedor, make_empresa, parana, acre):
        make_empresa("Curitibana", cidade=parana)
        make_empresa("Acreana", cidade=acre)
        login_as(vendedor)

        assert [c["name"] for c in api.get(f"{URL}?uf=PR").data["results"]] == ["Curitibana"]
        assert [c["name"] for c in api.get(f"{URL}?city={parana.id}").data["results"]] == [
            "Curitibana"
        ]

    def test_categoria_por_slug(self, api, login_as, vendedor, make_empresa, dentistas):
        make_empresa("Com categoria", categoria=dentistas)
        make_empresa("Sem categoria")
        login_as(vendedor)

        r = api.get(f"{URL}?category=dentistas")
        assert [c["name"] for c in r.data["results"]] == ["Com categoria"]

    def test_nome_ignora_acento_e_caixa(self, api, login_as, vendedor, make_empresa):
        make_empresa("Clínica São José")
        make_empresa("Auto Center")
        login_as(vendedor)

        assert api.get(f"{URL}?q=sao jose").data["count"] == 1

    def test_tem_telefone_nos_dois_sentidos(self, api, login_as, vendedor, make_empresa):
        make_empresa("Com telefone", telefone="+554133330000")
        make_empresa("Sem telefone")
        login_as(vendedor)

        assert [c["name"] for c in api.get(f"{URL}?has_phone=true").data["results"]] == [
            "Com telefone"
        ]
        assert [c["name"] for c in api.get(f"{URL}?has_phone=false").data["results"]] == [
            "Sem telefone"
        ]

    def test_telefone_invalido_nao_conta_como_telefone(self, api, login_as, vendedor, make_empresa):
        empresa = make_empresa("Telefone reprovado", telefone="41-3333")
        empresa.contacts.update(verification_status=CompanyContact.VerificationStatus.INVALID)
        login_as(vendedor)

        assert api.get(f"{URL}?has_phone=true").data["count"] == 0
        assert api.get(URL).data["results"][0]["phone"] is None

    def test_site_nao_identificado_nao_inclui_nao_verificado(
        self, api, login_as, vendedor, make_empresa
    ):
        """A regra que sustenta a credibilidade do produto, agora como filtro."""
        make_empresa("Sem site nas fontes", website_status=Company.WebsiteStatus.NOT_FOUND)
        make_empresa("Nunca verificada", website_status=Company.WebsiteStatus.NOT_CHECKED)
        login_as(vendedor)

        r = api.get(f"{URL}?site=not_found")
        assert [c["name"] for c in r.data["results"]] == ["Sem site nas fontes"]

        r = api.get(f"{URL}?site=not_checked")
        assert [c["name"] for c in r.data["results"]] == ["Nunca verificada"]

    def test_site_com_problemas(self, api, login_as, vendedor, make_empresa):
        quebrada = make_empresa(
            "Site fora do ar",
            site="https://forado.ar",
            website_status=Company.WebsiteStatus.FOUND,
        )
        ok = make_empresa(
            "Site no ar", site="https://noar.com", website_status=Company.WebsiteStatus.FOUND
        )
        WebsiteScan.objects.create(company=quebrada, status=WebsiteScan.Status.UNREACHABLE)
        WebsiteScan.objects.create(company=ok, status=WebsiteScan.Status.OK)
        login_as(vendedor)

        assert [c["name"] for c in api.get(f"{URL}?site=broken").data["results"]] == [
            "Site fora do ar"
        ]

    def test_recusa_do_guard_de_ssrf_nao_e_site_com_problema(
        self, api, login_as, vendedor, make_empresa
    ):
        """`BLOCKED` é evento de segurança, não diagnóstico comercial."""
        empresa = make_empresa("Endereço recusado", site="https://interno.local")
        WebsiteScan.objects.create(company=empresa, status=WebsiteScan.Status.BLOCKED)
        login_as(vendedor)

        assert api.get(f"{URL}?site=broken").data["count"] == 0

    def test_faixa_de_score(self, api, login_as, vendedor, make_empresa):
        make_empresa("Alta", score=90)
        make_empresa("Média", score=50)
        login_as(vendedor)

        assert [c["name"] for c in api.get(f"{URL}?score_min=60").data["results"]] == ["Alta"]
        assert [c["name"] for c in api.get(f"{URL}?score_max=60").data["results"]] == ["Média"]

    def test_oportunidade_por_codigo(self, api, login_as, vendedor, make_empresa):
        empresa = make_empresa("Sem site")
        make_empresa("Sem oportunidade")
        tipo = OpportunityType.objects.create(
            code="site-institucional", name="Site institucional", rule_code="sem_site"
        )
        Opportunity.objects.create(company=empresa, type=tipo, status=Opportunity.Status.OPEN)
        login_as(vendedor)

        r = api.get(f"{URL}?opportunity=site-institucional")
        assert [c["name"] for c in r.data["results"]] == ["Sem site"]

    def test_combinar_filtros_e_o_cenario_de_homologacao(
        self, api, login_as, vendedor, make_empresa, parana, acre, dentistas
    ):
        """ "Dentistas em Curitiba sem site e com telefone" — em uma requisição."""
        make_empresa(
            "Alvo",
            cidade=parana,
            categoria=dentistas,
            telefone="+554133330000",
            website_status=Company.WebsiteStatus.NOT_FOUND,
        )
        make_empresa(
            "Outra cidade",
            cidade=acre,
            categoria=dentistas,
            telefone="+555533330000",
            website_status=Company.WebsiteStatus.NOT_FOUND,
        )
        make_empresa(
            "Sem telefone",
            cidade=parana,
            categoria=dentistas,
            website_status=Company.WebsiteStatus.NOT_FOUND,
        )
        login_as(vendedor)

        r = api.get(f"{URL}?uf=PR&category=dentistas&site=not_found&has_phone=true")
        assert [c["name"] for c in r.data["results"]] == ["Alvo"]


class TestCrmNaListagem:
    def test_marca_quem_ja_e_lead_desta_organizacao(
        self, api, login_as, vendedor, make_empresa, org
    ):
        criar_funil_padrao(org)
        empresa = make_empresa("Já prospectada")
        make_empresa("Ainda não")
        services.create_lead(organization=org, company=empresa)
        login_as(vendedor)

        por_nome = {c["name"]: c for c in api.get(URL).data["results"]}

        assert por_nome["Já prospectada"]["lead_stage_code"] == "novo"
        assert por_nome["Ainda não"]["lead_id"] is None

    def test_lead_de_outra_organizacao_nao_vaza(
        self, api, login_as, vendedor, make_empresa, make_org, org
    ):
        """A empresa é global; a relação comercial não. É a fronteira do ADR-0007."""
        outra = make_org("Concorrente")
        criar_funil_padrao(outra)
        empresa = make_empresa("Disputada")
        services.create_lead(organization=outra, company=empresa)
        login_as(vendedor)

        linha = api.get(URL).data["results"][0]
        assert linha["lead_id"] is None
        assert linha["lead_stage_code"] is None

    def test_filtra_quem_ainda_nao_esta_no_crm(self, api, login_as, vendedor, make_empresa, org):
        criar_funil_padrao(org)
        empresa = make_empresa("Já prospectada")
        make_empresa("Ainda não")
        services.create_lead(organization=org, company=empresa)
        login_as(vendedor)

        assert [c["name"] for c in api.get(f"{URL}?in_crm=false").data["results"]] == ["Ainda não"]
        assert [c["name"] for c in api.get(f"{URL}?stage=novo").data["results"]] == [
            "Já prospectada"
        ]


class TestDetalhe:
    def test_traz_contatos_e_endereco(
        self, api, login_as, vendedor, make_empresa, parana, dentistas
    ):
        empresa = make_empresa(
            "Clínica Sorriso",
            cidade=parana,
            categoria=dentistas,
            telefone="+554133330000",
            site="https://sorriso.com.br",
        )
        login_as(vendedor)

        dados = api.get(f"{URL}{empresa.id}/").data

        assert dados["phone"] == "+554133330000"
        assert [c["kind"] for c in dados["contacts"]] == ["PHONE"]
        assert dados["addresses"][0]["uf"] == "PR"
        assert dados["websites"][0]["domain"] == "sorriso.com.br"
        assert [c["slug"] for c in dados["categories"]] == ["dentistas"]

    def test_e_somente_leitura(self, api, login_as, vendedor, make_empresa):
        empresa = make_empresa("Clínica")
        login_as(vendedor)

        assert api.patch(f"{URL}{empresa.id}/", {"name": "Outro"}, format="json").status_code == 405


class TestConsultas:
    def test_numero_de_consultas_nao_cresce_com_as_linhas(
        self, api, login_as, vendedor, make_empresa, parana, dentistas
    ):
        """O método da Etapa 14: contar com 10 e com 30. Se subir, há N+1."""
        criar_funil_padrao(vendedor.memberships.get().organization)
        login_as(vendedor)

        def carrega(quantas: int) -> int:
            Company.objects.all().delete()
            for i in range(quantas):
                make_empresa(
                    f"Empresa {i}",
                    cidade=parana,
                    categoria=dentistas,
                    telefone=f"+55413333{i:04d}",
                    score=i,
                )
            from django.db import connection, reset_queries
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as capturadas:
                assert api.get(f"{URL}?page_size=50").status_code == 200
            reset_queries()
            return len(capturadas)

        assert carrega(10) == carrega(30)


class TestExportacao:
    def test_csv_traz_cabecalho_e_telefone(self, api, login_as, vendedor, make_empresa, parana):
        make_empresa("Clínica Sorriso", cidade=parana, telefone="+554133330000", score=94)
        login_as(vendedor)

        r = api.get(f"{URL}export/")

        assert r.status_code == 200
        assert r["Content-Disposition"].endswith('filename="empresas.csv"')
        conteudo = b"".join(r.streaming_content).decode()
        assert "Telefone" in conteudo.splitlines()[0]
        assert "+554133330000" in conteudo

    def test_csv_respeita_o_filtro_da_tela(
        self, api, login_as, vendedor, make_empresa, parana, acre
    ):
        make_empresa("Curitibana", cidade=parana)
        make_empresa("Acreana", cidade=acre)
        login_as(vendedor)

        conteudo = b"".join(api.get(f"{URL}export/?uf=PR").streaming_content).decode()

        assert "Curitibana" in conteudo
        assert "Acreana" not in conteudo

    def test_csv_nunca_afirma_que_a_empresa_nao_tem_site(
        self, api, login_as, vendedor, make_empresa
    ):
        """A frase sai do produto e vira 'verdade' na planilha de terceiros."""
        make_empresa("Sem site", website_status=Company.WebsiteStatus.NOT_FOUND)
        login_as(vendedor)

        conteudo = b"".join(api.get(f"{URL}export/").streaming_content).decode()

        assert "não identificado nas fontes analisadas" in conteudo
        assert "não tem site" not in conteudo

    def test_exportacao_fica_registrada(self, api, login_as, vendedor, make_empresa):
        from apps.core.models import AuditLog

        make_empresa("Clínica")
        login_as(vendedor)

        api.get(f"{URL}export/?uf=PR")

        registro = AuditLog.objects.get(action=AuditLog.Action.EXPORT)
        assert registro.actor == vendedor
        assert registro.changes["filtros"] == {"uf": "PR"}
