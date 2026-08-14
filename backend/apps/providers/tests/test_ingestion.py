"""O pipeline do ADR-0003 de ponta a ponta, sem rede.

A propriedade que mais importa aqui é a idempotência: reprocessar a mesma busca não pode
criar empresa duplicada. Ela vem da UniqueConstraint(provider, external_id) no banco, e não
de checagem em Python — então precisa ser exercitada contra o banco de verdade.
"""

import pytest

from apps.companies.models import Company, CompanyContact
from apps.providers.ingestion import ingest_city
from apps.providers.models import CompanySource, ProviderUsage

pytestmark = pytest.mark.django_db


def _varrer(fonte_mock, linha_mock, londrina, dentistas, **kwargs):
    return ingest_city(
        provider=fonte_mock,
        provider_row=linha_mock,
        city=londrina,
        tags=dentistas,
        **kwargs,
    )


class TestPrimeiraVarredura:
    def test_cria_as_empresas(self, fonte_mock, linha_mock, londrina, dentistas):
        relatorio = _varrer(fonte_mock, linha_mock, londrina, dentistas)

        # São cinco elementos no mock, mas um não tem `name`: geometria solta, descartada
        # ainda no provider.
        assert relatorio.created == 4
        assert Company.objects.count() == 4

    def test_grava_a_procedencia_de_cada_uma(self, fonte_mock, linha_mock, londrina, dentistas):
        _varrer(fonte_mock, linha_mock, londrina, dentistas)

        assert CompanySource.objects.count() == 4
        fonte = CompanySource.objects.get(external_id="node/1001")
        assert fonte.company.name == "Clínica Odontológica São José"
        assert fonte.raw_payload["tags"]["amenity"] == "dentist"
        assert fonte.expires_at is None  # PERSIST não expira

    def test_normaliza_telefone_site_e_endereco(self, fonte_mock, linha_mock, londrina, dentistas):
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        empresa = Company.objects.get(name="Clínica Odontológica São José")

        assert empresa.contacts.get(kind=CompanyContact.Kind.PHONE).value_normalized == (
            "+554333241000"
        )
        assert empresa.websites.get().domain == "saojose-odonto.com.br"

        endereco = empresa.addresses.get()
        assert (endereco.city, endereco.street, endereco.postal_code) == (
            londrina,
            "Avenida Higienópolis",
            "86015010",
        )
        assert endereco.location.y == pytest.approx(-23.3164)

    def test_le_as_duas_grafias_de_tag_e_valor_multiplo(
        self, fonte_mock, linha_mock, londrina, dentistas
    ):
        """OSM tem `phone` e `contact:phone`, e separa valores múltiplos por `;`."""
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        empresa = Company.objects.get(name="Odontologia Integrada Paraná")

        telefones = set(
            empresa.contacts.filter(kind=CompanyContact.Kind.PHONE).values_list(
                "value_normalized", flat=True
            )
        )
        assert telefones == {"+554333252000", "+5543999998888"}
        assert empresa.contacts.get(kind=CompanyContact.Kind.EMAIL).value_normalized == (
            "contato@odontoparana.com.br"
        )

    def test_telefone_invalido_nao_entra(self, fonte_mock, linha_mock, londrina, dentistas):
        """Melhor sem telefone do que com um que não existe: '43 9999-8888' é celular
        sem o nono dígito, e fixo brasileiro não começa com 9."""
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        assert Company.objects.get(name="Consultório Tanaka").contacts.count() == 0

    def test_sem_site_nao_afirma_ausencia(self, fonte_mock, linha_mock, londrina, dentistas):
        """Ausência no OSM não é ausência no mundo (ADR-0004). Quem decide é o scanner."""
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        empresa = Company.objects.get(name="Dr. Sérgio Yokoyama")

        assert empresa.website_status == Company.WebsiteStatus.NOT_CHECKED
        assert empresa.website_status != Company.WebsiteStatus.NOT_FOUND

    def test_com_site_ja_nasce_marcada(self, fonte_mock, linha_mock, londrina, dentistas):
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        empresa = Company.objects.get(name="Clínica Odontológica São José")
        assert empresa.website_status == Company.WebsiteStatus.FOUND


class TestIdempotencia:
    def test_varrer_de_novo_nao_duplica(self, fonte_mock, linha_mock, londrina, dentistas):
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        segundo = _varrer(fonte_mock, linha_mock, londrina, dentistas)

        assert segundo.created == 0
        assert segundo.updated == 4
        assert Company.objects.count() == 4
        assert CompanySource.objects.count() == 4

    def test_nao_duplica_satelite(self, fonte_mock, linha_mock, londrina, dentistas):
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        _varrer(fonte_mock, linha_mock, londrina, dentistas)

        empresa = Company.objects.get(name="Clínica Odontológica São José")
        assert empresa.contacts.count() == 1
        assert empresa.websites.count() == 1
        assert empresa.addresses.count() == 1

    def test_redescoberta_atualiza_last_seen(self, fonte_mock, linha_mock, londrina, dentistas):
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        antes = Company.objects.get(name="Clínica Odontológica São José").last_seen_at

        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        depois = Company.objects.get(name="Clínica Odontológica São José").last_seen_at

        assert depois > antes

    def test_redescoberta_nao_sobrescreve_o_que_ja_havia(
        self, fonte_mock, linha_mock, londrina, dentistas
    ):
        """Fonte pobre não apaga o que uma fonte boa trouxe antes."""
        _varrer(fonte_mock, linha_mock, londrina, dentistas)
        empresa = Company.objects.get(name="Dr. Sérgio Yokoyama")
        empresa.legal_name = "Sérgio Yokoyama Odontologia ME"
        empresa.save()

        _varrer(fonte_mock, linha_mock, londrina, dentistas)

        empresa.refresh_from_db()
        assert empresa.legal_name == "Sérgio Yokoyama Odontologia ME"


class TestDedupNaIngestao:
    def test_empresa_ja_existente_e_reconhecida_em_vez_de_recriada(
        self, fonte_mock, linha_mock, londrina, dentistas
    ):
        """Mesma clínica já no banco por outro caminho: a dedup pega pelo nome + cidade."""
        from apps.companies.models import CompanyAddress

        existente = Company.objects.create(name="Clinica Odontologica Sao Jose")
        CompanyAddress.objects.create(company=existente, city=londrina)

        relatorio = _varrer(fonte_mock, linha_mock, londrina, dentistas)

        assert relatorio.created == 3
        assert relatorio.updated == 1
        assert not Company.objects.filter(name="Clínica Odontológica São José").exists()
        assert existente.contacts.count() == 1  # herdou o telefone da fonte

    def test_correspondencia_possivel_nao_funde_sozinha(
        self, fonte_mock, linha_mock, londrina, dentistas
    ):
        """POSSIBLE vai para revisão humana e não vira empresa nem merge (PROJECT_PLAN §4)."""
        from apps.companies.models import CompanyAddress

        # "São Pedro" x "São José" mede 0.676: acima de POSSIBLE, abaixo de PROBABLE.
        parecida = Company.objects.create(name="Clínica Odontológica São Pedro")
        CompanyAddress.objects.create(company=parecida, city=londrina)

        relatorio = _varrer(fonte_mock, linha_mock, londrina, dentistas)

        assert relatorio.review == 1
        assert not Company.objects.filter(name="Clínica Odontológica São José").exists()
        assert not CompanySource.objects.filter(external_id="node/1001").exists()


class TestConsumo:
    def test_contabiliza_requisicao_por_organizacao(
        self, fonte_mock, linha_mock, londrina, dentistas, org
    ):
        _varrer(fonte_mock, linha_mock, londrina, dentistas, organization=org)

        uso = ProviderUsage.objects.get(provider=linha_mock, organization=org)
        assert uso.request_count == 1
        assert uso.error_count == 0

    def test_varreduras_no_mesmo_dia_somam_na_mesma_linha(
        self, fonte_mock, linha_mock, londrina, dentistas, org
    ):
        _varrer(fonte_mock, linha_mock, londrina, dentistas, organization=org)
        _varrer(fonte_mock, linha_mock, londrina, dentistas, organization=org)

        assert ProviderUsage.objects.count() == 1
        assert ProviderUsage.objects.get().request_count == 2

    def test_sem_organizacao_nao_quebra(self, fonte_mock, linha_mock, londrina, dentistas):
        """Shell e teste rodam sem organização — não é motivo para derrubar a varredura."""
        assert _varrer(fonte_mock, linha_mock, londrina, dentistas).created == 4
        assert ProviderUsage.objects.count() == 0


class TestResiliencia:
    def test_item_ruim_nao_derruba_a_varredura(
        self, fonte_mock, linha_mock, londrina, dentistas, monkeypatch
    ):
        """Um endereço torto no item 2 não pode desfazer os que entraram certos.

        Cada resultado é sua própria transação, justamente para isso.
        """
        from apps.providers import ingestion

        original = ingestion._criar
        chamadas = {"n": 0}

        def _explodir_no_segundo(candidato, city):
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                raise ValueError("payload torto")
            return original(candidato, city)

        monkeypatch.setattr(ingestion, "_criar", _explodir_no_segundo)

        relatorio = _varrer(fonte_mock, linha_mock, londrina, dentistas)

        assert relatorio.created == 3
        assert relatorio.skipped == 1
        assert relatorio.reasons["erro"] == 1
        assert Company.objects.count() == 3

    def test_erro_conta_como_erro_no_consumo(
        self, fonte_mock, linha_mock, londrina, dentistas, org, monkeypatch
    ):
        from apps.providers import ingestion

        monkeypatch.setattr(ingestion, "_criar", lambda *a: (_ for _ in ()).throw(ValueError("x")))
        _varrer(fonte_mock, linha_mock, londrina, dentistas, organization=org)

        assert ProviderUsage.objects.get().error_count == 4


def test_seed_providers_e_idempotente(db):
    """É o comando que todo mundo roda primeiro; tem de poder rodar duas vezes."""
    from django.core.management import call_command

    from apps.providers.models import Provider

    call_command("seed_providers", verbosity=0)
    call_command("seed_providers", verbosity=0)

    assert Provider.objects.filter(slug="osm-overpass").count() == 1
    assert Provider.objects.filter(slug="mock").count() == 1

    osm = Provider.objects.get(slug="osm-overpass")
    assert osm.is_enabled
    assert osm.rate_limit_per_second == 1  # política de uso justo do OSM (ADR-0004)
    assert "OpenStreetMap" in osm.config["attribution"]
