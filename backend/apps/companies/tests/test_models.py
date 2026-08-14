"""As constraints valem no banco, não só na aplicação (CLAUDE.md).

Cada teste aqui tenta gravar o que não pode e exige `IntegrityError`. Validação só em
Python passaria por cima de um `bulk_create`, de uma task Celery ou de um `psql` aberto às
pressas — e é justamente aí que o dado sujo entra.
"""

import pytest
from django.contrib.gis.geos import Point
from django.db.utils import IntegrityError

from apps.companies.models import (
    Category,
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanySocialProfile,
    CompanyWebsite,
)
from apps.geography.models import City, Region, State

pytestmark = pytest.mark.django_db


@pytest.fixture
def cidade(db):
    parana = State.objects.create(ibge_code="41", uf="PR", name="Paraná", region=Region.SUL)
    return City.objects.create(ibge_code="4113700", name="Londrina", state=parana)


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Clínica São José")


class TestCompany:
    def test_nome_normalizado_sai_do_nome(self, empresa):
        assert empresa.normalized_name == "clinica sao jose"

    def test_renomear_com_update_fields_atualiza_o_normalizado(self, empresa):
        """Mesmo furo de `geography.City`: o derivado tem de acompanhar sua origem."""
        empresa.name = "Clínica São João"
        empresa.save(update_fields=["name"])

        empresa.refresh_from_db()
        assert empresa.normalized_name == "clinica sao joao"

    def test_duas_empresas_sem_cnpj_convivem(self):
        """CNPJ nulo é comum: MEI sem registro na fonte, empresa que só existe no OSM."""
        Company.objects.create(name="Uma")
        Company.objects.create(name="Outra")
        assert Company.objects.filter(tax_id__isnull=True).count() == 2

    def test_cnpj_repetido_e_recusado_pelo_banco(self):
        Company.objects.create(name="Uma", tax_id="11222333000181")
        with pytest.raises(IntegrityError):
            Company.objects.create(name="Outra", tax_id="11222333000181")

    def test_cnpj_fora_do_formato_e_recusado_pelo_banco(self):
        with pytest.raises(IntegrityError):
            Company.objects.create(name="Torta", tax_id="112223330001")

    @pytest.mark.parametrize("nota", ["-0.1", "5.1"])
    def test_nota_fora_de_0_a_5_e_recusada(self, nota):
        with pytest.raises(IntegrityError):
            Company.objects.create(name="Nota errada", rating=nota)

    def test_situacao_de_site_nao_afirma_ausencia(self):
        """CLAUDE.md proíbe dizer que a empresa não tem site — o rótulo é literal."""
        rotulo = dict(Company.WebsiteStatus.choices)[Company.WebsiteStatus.NOT_FOUND]
        assert str(rotulo) == "Site oficial não identificado nas fontes analisadas"


class TestCompanyContact:
    def test_mesmo_contato_duas_vezes_e_recusado(self, empresa):
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="(43) 99999-8888",
            value_normalized="+5543999998888",
        )
        with pytest.raises(IntegrityError):
            CompanyContact.objects.create(
                company=empresa,
                kind=CompanyContact.Kind.PHONE,
                value_raw="43 99999 8888",  # forma crua diferente, mesmo número
                value_normalized="+5543999998888",
            )

    def test_mesmo_numero_como_telefone_e_whatsapp_convive(self, empresa):
        """São canais distintos: falar por voz e por mensagem não são a mesma abordagem."""
        for kind in (CompanyContact.Kind.PHONE, CompanyContact.Kind.WHATSAPP):
            CompanyContact.objects.create(
                company=empresa,
                kind=kind,
                value_raw="(43) 99999-8888",
                value_normalized="+5543999998888",
            )
        assert empresa.contacts.count() == 2

    def test_confianca_fora_de_0_a_1_e_recusada(self, empresa):
        with pytest.raises(IntegrityError):
            CompanyContact.objects.create(
                company=empresa,
                kind=CompanyContact.Kind.EMAIL,
                value_raw="a@b.com",
                value_normalized="a@b.com",
                confidence="1.5",
            )


class TestCompanyAddress:
    def test_endereco_com_geometria(self, empresa, cidade):
        endereco = CompanyAddress.objects.create(
            company=empresa, city=cidade, street="Rua X", location=Point(-51.16, -23.31)
        )
        assert endereco.location.x == pytest.approx(-51.16)

    def test_apagar_cidade_com_endereco_e_bloqueado(self, empresa, cidade):
        """`PROTECT`: perder a base do IBGE não pode arrastar endereço de empresa junto."""
        CompanyAddress.objects.create(company=empresa, city=cidade)
        with pytest.raises(IntegrityError):
            cidade.delete()

    def test_cep_fora_do_formato_e_recusado(self, empresa, cidade):
        with pytest.raises(IntegrityError):
            CompanyAddress.objects.create(company=empresa, city=cidade, postal_code="8601")

    def test_cep_vazio_e_permitido(self, empresa, cidade):
        """Fonte pública quase nunca traz CEP — exigir seria descartar empresa boa."""
        assert CompanyAddress.objects.create(company=empresa, city=cidade).postal_code == ""

    def test_apagar_empresa_leva_o_endereco_junto(self, empresa, cidade):
        """`CASCADE` no satélite: endereço sem empresa não significa nada."""
        CompanyAddress.objects.create(company=empresa, city=cidade)
        empresa.delete()
        assert CompanyAddress.objects.count() == 0


class TestCompanyWebsite:
    def test_mesmo_dominio_duas_vezes_na_mesma_empresa_e_recusado(self, empresa):
        CompanyWebsite.objects.create(
            company=empresa, url="https://exemplo.com.br", domain="exemplo.com.br"
        )
        with pytest.raises(IntegrityError):
            CompanyWebsite.objects.create(
                company=empresa, url="https://exemplo.com.br/contato", domain="exemplo.com.br"
            )


def test_representacao_em_texto_de_todos_os_models(empresa, cidade):
    """O admin chama `__str__` em toda listagem — um que quebre derruba a tela inteira."""
    categoria = Category.objects.create(slug="dentista", name="Dentista")
    objetos = [
        empresa,
        categoria,
        CompanyAddress.objects.create(company=empresa, city=cidade, street="Rua X", number="10"),
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="(43) 99999-8888",
            value_normalized="+5543999998888",
        ),
        CompanyWebsite.objects.create(
            company=empresa, url="https://exemplo.com.br", domain="exemplo.com.br"
        ),
        CompanySocialProfile.objects.create(
            company=empresa,
            network=CompanySocialProfile.Network.INSTAGRAM,
            url="https://instagram.com/exemplo",
            handle="@exemplo",
        ),
        CompanyCategory.objects.create(company=empresa, category=categoria),
    ]
    for obj in objetos:
        assert str(obj).strip(), f"{type(obj).__name__} devolveu texto vazio"


class TestCategory:
    def test_arvore_de_categorias(self):
        saude = Category.objects.create(slug="saude", name="Saúde")
        odonto = Category.objects.create(slug="odontologia", name="Odontologia", parent=saude)
        assert list(saude.children.all()) == [odonto]

    def test_categoria_em_uso_nao_pode_ser_apagada(self, empresa):
        """`PROTECT`: apagar categoria classificada arrastaria a classificação de empresas."""
        categoria = Category.objects.create(slug="dentista", name="Dentista")
        CompanyCategory.objects.create(company=empresa, category=categoria)
        with pytest.raises(IntegrityError):
            categoria.delete()

    def test_mesma_categoria_duas_vezes_na_empresa_e_recusada(self, empresa):
        categoria = Category.objects.create(slug="dentista", name="Dentista")
        CompanyCategory.objects.create(company=empresa, category=categoria)
        with pytest.raises(IntegrityError):
            CompanyCategory.objects.create(company=empresa, category=categoria)
