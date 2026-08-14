"""A API do CRM e o isolamento que ela obriga.

Histórico comercial é o dado mais sensível do produto: o que uma organização falou com quem,
e quando. Vazamento aqui é contratual, não estético.
"""

import pytest

from apps.accounts.models import Role
from apps.companies.models import Company, CompanyContact
from apps.crm import services
from apps.crm.management.commands.seed_pipeline import criar_funil_padrao
from apps.crm.models import Interaction, Lead, SuppressionEntry

pytestmark = pytest.mark.django_db


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


class TestLead:
    def test_cria_pelo_endpoint(self, api, login_as, vendedor, funil, empresa):
        login_as(vendedor)
        r = api.post("/api/v1/crm/leads/", {"company": str(empresa.id)}, format="json")

        assert r.status_code == 201, r.data
        assert r.data["stage_code"] == "novo"
        assert Lead.objects.get().owner == vendedor

    def test_leitor_nao_cria(self, api, login_as, leitor, funil, empresa):
        login_as(leitor)
        assert (
            api.post("/api/v1/crm/leads/", {"company": str(empresa.id)}, format="json").status_code
            == 403
        )

    def test_empresa_inexistente_e_400(self, api, login_as, vendedor, funil):
        import uuid

        login_as(vendedor)
        r = api.post("/api/v1/crm/leads/", {"company": str(uuid.uuid4())}, format="json")
        assert r.status_code == 400

    def test_move_de_estagio(self, api, login_as, vendedor, funil, empresa, org):
        lead = services.create_lead(organization=org, company=empresa)
        login_as(vendedor)

        r = api.post(
            f"/api/v1/crm/leads/{lead.id}/move/",
            {"stage": str(funil.stages.get(code="qualificado").id)},
            format="json",
        )

        assert r.status_code == 200
        assert r.data["stage_code"] == "qualificado"

    def test_recusa_estagio_de_outro_funil(
        self, api, login_as, vendedor, funil, empresa, org, make_org
    ):
        lead = services.create_lead(organization=org, company=empresa)
        alheio = criar_funil_padrao(make_org("Concorrente"))
        login_as(vendedor)

        r = api.post(
            f"/api/v1/crm/leads/{lead.id}/move/",
            {"stage": str(alheio.stages.first().id)},
            format="json",
        )
        assert r.status_code == 400


class TestHistorico:
    def test_registra_e_lista(self, api, login_as, vendedor, funil, empresa, org):
        lead = services.create_lead(organization=org, company=empresa)
        login_as(vendedor)

        r = api.post(
            f"/api/v1/crm/leads/{lead.id}/interactions/",
            {
                "kind": Interaction.Kind.CALL,
                "description": "Falei com o dono",
                "outcome": "ANSWERED",
            },
            format="json",
        )
        assert r.status_code == 201

        listagem = api.get(f"/api/v1/crm/leads/{lead.id}/interactions/")
        assert listagem.data["count"] == 2  # a criação do lead também é evento
        assert listagem.data["results"][0]["kind_label"] == "Ligação"

    def test_anotacao_editavel_e_separada_do_historico(
        self, api, login_as, vendedor, funil, empresa, org
    ):
        """Interação é evento (append-only); anotação é conhecimento, e se corrige."""
        lead = services.create_lead(organization=org, company=empresa)
        login_as(vendedor)

        r = api.post(
            f"/api/v1/crm/leads/{lead.id}/notes/",
            {"body": "O dono é irmão do concorrente."},
            format="json",
        )

        assert r.status_code == 201
        assert api.get(f"/api/v1/crm/leads/{lead.id}/notes/").data["count"] == 1


class TestSupressaoNaApi:
    def test_admin_registra_e_encerra_leads(self, api, login_as, admin, funil, empresa, org):
        services.create_lead(organization=org, company=empresa)
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )
        login_as(admin)

        r = api.post(
            "/api/v1/crm/suppressions/",
            {
                "identifier_kind": SuppressionEntry.Kind.PHONE,
                "identifier_value": "+554333241000",
                "reason": "Pediu opt-out",
            },
            format="json",
        )

        assert r.status_code == 201
        assert r.data["leads_encerrados"] == 1

    def test_vendedor_nao_registra_supressao(self, api, login_as, vendedor, funil):
        """Conformidade não é rotina comercial."""
        login_as(vendedor)
        r = api.post(
            "/api/v1/crm/suppressions/",
            {"identifier_kind": "PHONE", "identifier_value": "+554333241000"},
            format="json",
        )
        assert r.status_code == 403

    def test_nao_ha_como_remover_pela_api(self, api, login_as, admin, org, funil):
        """Tirar alguém de uma lista de opt-out precisa de decisão explícita, não de botão."""
        entrada, _ = services.suppress(
            organization=org, identifier_kind="PHONE", identifier_value="+554333241000"
        )
        login_as(admin)

        assert api.delete(f"/api/v1/crm/suppressions/{entrada.id}/").status_code == 405

    def test_lead_de_empresa_suprimida_e_403(self, api, login_as, vendedor, funil, empresa, org):
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.COMPANY,
            identifier_value=str(empresa.pk),
        )
        login_as(vendedor)

        r = api.post("/api/v1/crm/leads/", {"company": str(empresa.id)}, format="json")

        # 403 e não 400: não é payload inválido, é proibição.
        assert r.status_code == 403
        assert "supressão" in r.data["detail"]


class TestIsolamento:
    def test_lead_de_outra_organizacao_responde_404(
        self, api, login_as, vendedor, make_org, empresa
    ):
        outra = make_org("Concorrente")
        criar_funil_padrao(outra)
        alheio = services.create_lead(organization=outra, company=empresa)

        login_as(vendedor)
        assert api.get(f"/api/v1/crm/leads/{alheio.id}/").status_code == 404

    def test_listagem_nao_mostra_lead_alheio(
        self, api, login_as, vendedor, funil, empresa, org, make_org
    ):
        outra = make_org("Concorrente")
        criar_funil_padrao(outra)
        services.create_lead(organization=outra, company=empresa)
        services.create_lead(organization=org, company=Company.objects.create(name="Minha"))

        login_as(vendedor)
        r = api.get("/api/v1/crm/leads/")

        assert r.data["count"] == 1
        assert r.data["results"][0]["company_name"] == "Minha"

    def test_historico_alheio_nao_vaza(self, api, login_as, vendedor, make_org, empresa):
        """O dado mais sensível do produto: com quem a concorrência falou, e quando."""
        outra = make_org("Concorrente")
        criar_funil_padrao(outra)
        alheio = services.create_lead(organization=outra, company=empresa)

        login_as(vendedor)
        assert api.get(f"/api/v1/crm/leads/{alheio.id}/interactions/").status_code == 404

    def test_supressao_alheia_nao_aparece(self, api, login_as, admin, make_org, org, funil):
        outra = make_org("Concorrente")
        services.suppress(
            organization=outra, identifier_kind="PHONE", identifier_value="+554399998888"
        )
        services.suppress(
            organization=org, identifier_kind="PHONE", identifier_value="+554333241000"
        )

        login_as(admin)
        r = api.get("/api/v1/crm/suppressions/")

        assert r.data["count"] == 1
        assert r.data["results"][0]["identifier_value"] == "+554333241000"


def test_funil_traz_a_contagem_por_estagio(
    api, login_as, org, make_user, make_member, funil, empresa
):
    """Sem anotação, a tela do funil faria uma consulta por coluna."""
    gestor = make_user("gestor@exemplo.com")
    make_member(gestor, org, role=Role.MANAGER)
    services.create_lead(organization=org, company=empresa)
    login_as(gestor)

    r = api.get("/api/v1/crm/pipelines/")

    estagios = {e["code"]: e["lead_count"] for e in r.data["results"][0]["stages"]}
    assert estagios["novo"] == 1
    assert estagios["ganho"] == 0
