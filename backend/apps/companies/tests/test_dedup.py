"""O resolvedor tem de errar para o lado certo.

Deixar de fundir gera uma duplicata, que se junta depois. Fundir errado destrói o histórico
de dois negócios, e desfazer é caro. Por isso os testes de "não deve bater" pesam tanto
quanto os de "deve bater".
"""

import pytest

from apps.companies.dedup import CompanyCandidate, MatchType, resolve
from apps.companies.models import Company, CompanyAddress, CompanyContact, CompanyWebsite
from apps.geography.models import City, Region, State

pytestmark = pytest.mark.django_db


@pytest.fixture
def parana(db):
    return State.objects.create(ibge_code="41", uf="PR", name="Paraná", region=Region.SUL)


@pytest.fixture
def londrina(parana):
    return City.objects.create(ibge_code="4113700", name="Londrina", state=parana)


@pytest.fixture
def maringa(parana):
    return City.objects.create(ibge_code="4115200", name="Maringá", state=parana)


@pytest.fixture
def fazer_empresa(db):
    def _fazer(nome, cidade=None, **kwargs):
        empresa = Company.objects.create(name=nome, **kwargs)
        if cidade is not None:
            CompanyAddress.objects.create(company=empresa, city=cidade)
        return empresa

    return _fazer


class TestCNPJ:
    def test_cnpj_igual_e_exact(self, fazer_empresa, londrina):
        existente = fazer_empresa("Clínica São José", londrina, tax_id="11222333000181")
        r = resolve(
            CompanyCandidate(name="Outro nome totalmente diferente", tax_id="11222333000181")
        )

        assert r.match_type == MatchType.EXACT
        assert r.company == existente
        assert r.signal == "tax_id"
        assert r.can_merge_automatically

    def test_cnpj_vence_o_nome(self, fazer_empresa, londrina):
        """Identificador legal manda sobre semelhança de texto, sempre."""
        fazer_empresa("Clínica São José", londrina)
        certa = fazer_empresa("Nome nada a ver", londrina, tax_id="11222333000181")

        r = resolve(
            CompanyCandidate(name="Clínica São José", tax_id="11222333000181", city=londrina)
        )
        assert r.company == certa
        assert r.match_type == MatchType.EXACT


class TestDominio:
    def test_dominio_igual_e_probable(self, fazer_empresa, londrina):
        existente = fazer_empresa("Clínica São José", londrina)
        CompanyWebsite.objects.create(
            company=existente, url="https://exemplo.com.br", domain="exemplo.com.br"
        )

        r = resolve(CompanyCandidate(name="Outra coisa", domain="exemplo.com.br"))
        assert (r.match_type, r.company, r.signal) == (MatchType.PROBABLE, existente, "domain")

    def test_dominio_nao_e_exact(self, fazer_empresa, londrina):
        """Franquia e grupo dividem site institucional — não dá para cravar."""
        existente = fazer_empresa("Rede X — Londrina", londrina)
        CompanyWebsite.objects.create(
            company=existente, url="https://rede.com.br", domain="rede.com.br"
        )

        assert resolve(
            CompanyCandidate(name="Rede X — Maringá", domain="rede.com.br")
        ).match_type != (MatchType.EXACT)


class TestTelefone:
    def test_telefone_na_mesma_cidade_e_probable(self, fazer_empresa, londrina):
        existente = fazer_empresa("Clínica São José", londrina)
        CompanyContact.objects.create(
            company=existente,
            kind=CompanyContact.Kind.PHONE,
            value_raw="(43) 3324-1000",
            value_normalized="+554333241000",
        )

        r = resolve(CompanyCandidate(name="Zzz", phones=("+554333241000",), city=londrina))
        assert (r.match_type, r.company, r.signal) == (
            MatchType.PROBABLE,
            existente,
            "phone+city",
        )

    def test_mesmo_telefone_em_cidade_diferente_nao_bate(self, fazer_empresa, londrina, maringa):
        """Linha desativada é reatribuída: a pizzaria que fechou vira a barbearia que abriu."""
        existente = fazer_empresa("Pizzaria Antiga", londrina)
        CompanyContact.objects.create(
            company=existente,
            kind=CompanyContact.Kind.PHONE,
            value_raw="(43) 3324-1000",
            value_normalized="+554333241000",
        )

        r = resolve(
            CompanyCandidate(name="Barbearia Nova", phones=("+554333241000",), city=maringa)
        )
        assert r.match_type == MatchType.NEW

    def test_telefone_sem_cidade_nao_e_usado(self, fazer_empresa, londrina):
        existente = fazer_empresa("Clínica", londrina)
        CompanyContact.objects.create(
            company=existente,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )

        assert resolve(CompanyCandidate(name="Zzz", phones=("+554333241000",))).is_new


class TestNome:
    def test_nome_praticamente_igual_e_probable(self, fazer_empresa, londrina):
        existente = fazer_empresa("Clínica Odontológica São José", londrina)

        r = resolve(CompanyCandidate(name="Clinica Odontologica Sao Jose", city=londrina))
        assert r.match_type == MatchType.PROBABLE
        assert r.company == existente
        assert r.score >= 0.85

    def test_nome_parecido_e_possible_e_nao_funde_sozinho(self, fazer_empresa, londrina):
        """O caso perigoso: parecido o bastante para suspeitar, não para agir.

        "São José" x "São Pedro" mede 0.676 — acima de POSSIBLE, abaixo de PROBABLE. Pode
        ser a mesma clínica com nome grafado de outro jeito, ou duas clínicas de santos
        diferentes na mesma rua. Máquina nenhuma resolve isso; vai para humano.
        """
        fazer_empresa("Clínica Odontológica São José", londrina)

        r = resolve(CompanyCandidate(name="Clínica Odontológica São Pedro", city=londrina))
        assert r.match_type == MatchType.POSSIBLE
        assert not r.can_merge_automatically

    def test_filial_em_bairro_diferente_e_empresa_nova(self, fazer_empresa, londrina):
        """Duas filiais são duas empresas: endereço, telefone e relacionamento próprios.

        Mede 0.531, abaixo de POSSIBLE. Fundir as duas apagaria a prospecção de uma delas.
        """
        fazer_empresa("Padaria Pão Quente Centro", londrina)
        assert resolve(CompanyCandidate(name="Padaria Pão Quente Zona Sul", city=londrina)).is_new

    def test_sufixo_juridico_nao_funde_sozinho(self, fazer_empresa, londrina):
        """ "Silva" x "Silva Ltda" mede 0.783: quase certamente a mesma, mas ainda revisão.

        É o preço da assimetria — deixar de fundir custa uma duplicata, fundir errado custa
        dois históricos. Se na prática der trabalho demais, é o limiar PROBABLE que baixa,
        com dado de uso na mão, não com palpite.
        """
        fazer_empresa("Supermercado Silva", londrina)

        r = resolve(CompanyCandidate(name="Supermercado Silva Ltda", city=londrina))
        assert r.match_type == MatchType.POSSIBLE

    def test_nome_diferente_e_empresa_nova(self, fazer_empresa, londrina):
        fazer_empresa("Clínica Odontológica São José", londrina)
        assert resolve(CompanyCandidate(name="Auto Peças Trevo", city=londrina)).is_new

    def test_nome_igual_em_cidade_diferente_nao_bate(self, fazer_empresa, londrina, maringa):
        """Blocking key: 'Farmácia Central' existe em quase todo município do país."""
        fazer_empresa("Farmácia Central", londrina)
        assert resolve(CompanyCandidate(name="Farmácia Central", city=maringa)).is_new

    def test_sem_cidade_o_nome_nao_e_comparado(self, fazer_empresa, londrina):
        """Sem recorte, a comparação varreria a tabela inteira — O(n²), PROJECT_PLAN §3.5."""
        fazer_empresa("Clínica Odontológica São José", londrina)
        assert resolve(CompanyCandidate(name="Clínica Odontológica São José")).is_new

    def test_escolhe_o_mais_parecido_entre_varios(self, fazer_empresa, londrina):
        fazer_empresa("Padaria Central", londrina)
        exata = fazer_empresa("Clínica Odontológica São José", londrina)
        fazer_empresa("Clínica Odontológica São Pedro", londrina)

        r = resolve(CompanyCandidate(name="Clínica Odontológica São José", city=londrina))
        assert r.company == exata


class TestEmpresaFundida:
    def test_empresa_ja_fundida_nao_volta_a_ser_candidata(self, fazer_empresa, londrina):
        """Senão o merge se desfaz sozinho na próxima descoberta."""
        sobrevivente = fazer_empresa("Clínica São José", londrina)
        fundida = fazer_empresa("Clinica Sao Jose", londrina, tax_id="11222333000181")
        fundida.status = Company.Status.MERGED
        fundida.merged_into = sobrevivente
        fundida.save()

        assert resolve(CompanyCandidate(name="X", tax_id="11222333000181")).is_new

    def test_site_de_empresa_fundida_nao_bate(self, fazer_empresa, londrina):
        fundida = fazer_empresa("Antiga", londrina, status=Company.Status.MERGED)
        CompanyWebsite.objects.create(
            company=fundida, url="https://exemplo.com.br", domain="exemplo.com.br"
        )
        assert resolve(CompanyCandidate(name="X", domain="exemplo.com.br")).is_new


def test_base_vazia_devolve_nova(londrina):
    assert resolve(CompanyCandidate(name="Qualquer", city=londrina)).is_new


def test_ordem_dos_sinais(fazer_empresa, londrina):
    """CNPJ > domínio > telefone > nome. Cada um aponta para uma empresa diferente."""
    por_cnpj = fazer_empresa("A", londrina, tax_id="11222333000181")
    por_dominio = fazer_empresa("B", londrina)
    CompanyWebsite.objects.create(company=por_dominio, url="https://x.com.br", domain="x.com.br")

    candidato = CompanyCandidate(
        name="B", tax_id="11222333000181", domain="x.com.br", city=londrina
    )
    assert resolve(candidato).company == por_cnpj

    sem_cnpj = CompanyCandidate(name="B", domain="x.com.br", city=londrina)
    assert resolve(sem_cnpj).company == por_dominio
