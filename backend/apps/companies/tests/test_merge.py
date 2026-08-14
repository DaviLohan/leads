"""Merge é a operação mais destrutiva do sistema.

Junta o histórico de dois registros e aposenta um. Se quebrar no meio, o banco não pode
ficar pela metade; se der certo, tem de ficar registrado. E colisão de satélite não pode
derrubar a transação inteira — é o caso comum, não o excepcional.
"""

import pytest
from django.db.utils import IntegrityError

from apps.companies.models import (
    Category,
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanyWebsite,
)
from apps.companies.services import MergeError, merge_companies
from apps.core.models import AuditLog
from apps.geography.models import City, Region, State

pytestmark = pytest.mark.django_db


@pytest.fixture
def londrina(db):
    parana = State.objects.create(ibge_code="41", uf="PR", name="Paraná", region=Region.SUL)
    return City.objects.create(ibge_code="4113700", name="Londrina", state=parana)


@pytest.fixture
def par(db):
    return Company.objects.create(name="Sobrevivente"), Company.objects.create(name="Duplicata")


def _telefone(empresa, numero, **kwargs):
    return CompanyContact.objects.create(
        company=empresa,
        kind=CompanyContact.Kind.PHONE,
        value_raw=numero,
        value_normalized=numero,
        **kwargs,
    )


class TestMerge:
    def test_move_os_satelites(self, par, londrina):
        sobrevivente, duplicata = par
        _telefone(duplicata, "+554333241000")
        CompanyWebsite.objects.create(company=duplicata, url="https://x.com.br", domain="x.com.br")
        CompanyAddress.objects.create(company=duplicata, city=londrina, street="Rua X")

        resultado = merge_companies(survivor=sobrevivente, duplicate=duplicata)

        assert sobrevivente.contacts.count() == 1
        assert sobrevivente.websites.count() == 1
        assert sobrevivente.addresses.count() == 1
        assert duplicata.contacts.count() == 0
        assert resultado.moved == {
            "CompanyContact": 1,
            "CompanyWebsite": 1,
            "CompanyAddress": 1,
        }

    def test_duplicata_vira_merged_apontando_para_a_sobrevivente(self, par):
        sobrevivente, duplicata = par
        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        duplicata.refresh_from_db()
        assert duplicata.status == Company.Status.MERGED
        assert duplicata.merged_into == sobrevivente

    def test_duplicata_nao_e_apagada(self, par):
        """Quem chegar pelo id antigo — link salvo, external_id de fonte — acha o caminho."""
        sobrevivente, duplicata = par
        pk_antigo = duplicata.pk
        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        assert Company.objects.filter(pk=pk_antigo).exists()

    def test_satelite_repetido_e_descartado_nao_derruba_a_transacao(self, par):
        """Mesmo telefone nas duas é o mesmo telefone — insistir violaria a UniqueConstraint."""
        sobrevivente, duplicata = par
        _telefone(sobrevivente, "+554333241000")
        _telefone(duplicata, "+554333241000")
        _telefone(duplicata, "+554399998888")

        resultado = merge_companies(survivor=sobrevivente, duplicate=duplicata)

        assert sobrevivente.contacts.count() == 2
        assert resultado.moved["CompanyContact"] == 1
        assert resultado.discarded["CompanyContact"] == 1

    def test_principal_da_sobrevivente_nao_e_disputado(self, par):
        sobrevivente, duplicata = par
        _telefone(sobrevivente, "+554333241000", is_primary=True)
        _telefone(duplicata, "+554399998888", is_primary=True)

        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        principais = sobrevivente.contacts.filter(is_primary=True)
        assert principais.count() == 1
        assert principais.first().value_normalized == "+554333241000"

    def test_categoria_repetida_e_descartada(self, par):
        sobrevivente, duplicata = par
        categoria = Category.objects.create(slug="dentista", name="Dentista")
        CompanyCategory.objects.create(company=sobrevivente, category=categoria)
        CompanyCategory.objects.create(company=duplicata, category=categoria)

        merge_companies(survivor=sobrevivente, duplicate=duplicata)
        assert sobrevivente.company_categories.count() == 1


class TestHeranca:
    def test_sobrevivente_adota_o_que_nao_tinha(self, par):
        sobrevivente, duplicata = par
        duplicata.legal_name = "Razão Social Ltda"
        duplicata.description = "Descrição vinda da outra fonte"
        duplicata.save()

        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        sobrevivente.refresh_from_db()
        assert sobrevivente.legal_name == "Razão Social Ltda"
        assert sobrevivente.description == "Descrição vinda da outra fonte"

    def test_nunca_sobrescreve_o_que_ja_havia(self, par):
        sobrevivente, duplicata = par
        sobrevivente.legal_name = "A Verdadeira Ltda"
        sobrevivente.save()
        duplicata.legal_name = "Outra Coisa Ltda"
        duplicata.save()

        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        sobrevivente.refresh_from_db()
        assert sobrevivente.legal_name == "A Verdadeira Ltda"

    def test_nome_nunca_e_herdado(self, par):
        """Nome é identidade — trocá-lo sozinho é decisão humana, não automática."""
        sobrevivente, duplicata = par
        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        sobrevivente.refresh_from_db()
        assert sobrevivente.name == "Sobrevivente"

    def test_cnpj_migra_e_a_duplicata_o_larga(self, par):
        """O CNPJ é único no banco: os dois não podem segurá-lo ao mesmo tempo."""
        sobrevivente, duplicata = par
        duplicata.tax_id = "11222333000181"
        duplicata.save()

        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        sobrevivente.refresh_from_db()
        duplicata.refresh_from_db()
        assert sobrevivente.tax_id == "11222333000181"
        assert duplicata.tax_id is None

    def test_avaliacao_vem_de_quem_tem_mais_resenhas(self, par):
        sobrevivente, duplicata = par
        sobrevivente.rating, sobrevivente.review_count = "4.0", 3
        sobrevivente.save()
        duplicata.rating, duplicata.review_count = "4.8", 120
        duplicata.save()

        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        sobrevivente.refresh_from_db()
        assert (str(sobrevivente.rating), sobrevivente.review_count) == ("4.8", 120)


class TestRecusas:
    def test_recusa_fundir_em_si_mesma(self, par):
        sobrevivente, _ = par
        with pytest.raises(MergeError, match="si mesma"):
            merge_companies(survivor=sobrevivente, duplicate=sobrevivente)

    def test_recusa_duplicata_ja_fundida(self, par):
        sobrevivente, duplicata = par
        outra = Company.objects.create(name="Terceira")
        merge_companies(survivor=sobrevivente, duplicate=duplicata)

        with pytest.raises(MergeError, match="já foi fundida"):
            merge_companies(survivor=outra, duplicate=duplicata)

    def test_recusa_cnpjs_diferentes(self, par):
        """Dois CNPJs válidos e distintos são duas pessoas jurídicas."""
        sobrevivente, duplicata = par
        sobrevivente.tax_id = "11222333000181"
        sobrevivente.save()
        duplicata.tax_id = "11444777000161"
        duplicata.save()

        with pytest.raises(MergeError, match="CNPJs diferentes"):
            merge_companies(survivor=sobrevivente, duplicate=duplicata)

    def test_banco_recusa_ponteiro_para_si_mesma(self, par):
        sobrevivente, _ = par
        with pytest.raises(IntegrityError):
            Company.objects.filter(pk=sobrevivente.pk).update(merged_into=sobrevivente.pk)


def test_cadeia_de_merge_e_achatada(par):
    """A -> B, depois B -> C: A tem de apontar direto para C, não dois saltos."""
    b, a = par
    c = Company.objects.create(name="Final")

    merge_companies(survivor=b, duplicate=a)
    merge_companies(survivor=c, duplicate=b)

    a.refresh_from_db()
    assert a.merged_into == c


def test_merge_grava_auditoria(par):
    sobrevivente, duplicata = par
    _telefone(duplicata, "+554333241000")

    merge_companies(survivor=sobrevivente, duplicate=duplicata)

    registro = AuditLog.objects.get(action=AuditLog.Action.MERGE)
    assert registro.object_id == sobrevivente.pk
    assert registro.changes["merged"] == str(duplicata.pk)
    assert registro.changes["merged_name"] == "Duplicata"
    assert registro.changes["moved"]["CompanyContact"] == 1


def test_merge_recusado_nao_deixa_rastro(par):
    """Falhar antes de tocar o banco: nada movido, nada auditado."""
    sobrevivente, duplicata = par
    sobrevivente.tax_id, duplicata.tax_id = "11222333000181", "11444777000161"
    sobrevivente.save()
    duplicata.save()

    with pytest.raises(MergeError):
        merge_companies(survivor=sobrevivente, duplicate=duplicata)

    duplicata.refresh_from_db()
    assert duplicata.status == Company.Status.ACTIVE
    assert not AuditLog.objects.filter(action=AuditLog.Action.MERGE).exists()
