"""A abstração e o contrato: consulta, normalização, retenção, limite e registro.

O `_post` do Overpass é dublado — nenhum teste sai para a rede (ADR-0003, regra 5).
"""

import json

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.providers.base import BaseProvider, RawResult, RetentionPolicy, SearchQuery
from apps.providers.mock import MockProvider
from apps.providers.models import CompanySource, Provider
from apps.providers.overpass import OverpassProvider
from apps.providers.registry import ProviderDisabledError, get_provider

pytestmark = pytest.mark.django_db


class TestConsultaOverpass:
    def test_usa_map_to_area_e_nao_area_por_tag(self):
        """Verificado contra o endpoint público: `area[tag]` responde 504, `map_to_area` não.

        O índice de áreas do Overpass não é feito para filtro por tag arbitrária.
        """
        consulta = OverpassProvider().build_query(
            SearchQuery(ibge_code="4113700", tags={"amenity": "dentist"})
        )

        assert "map_to_area" in consulta
        assert 'area["IBGE:GEOCODIGO"' not in consulta
        assert 'rel["IBGE:GEOCODIGO"="4113700"]' in consulta
        assert '["boundary"="administrative"]' in consulta
        assert '["amenity"="dentist"]' in consulta
        assert "out center tags" in consulta

    def test_liga_as_bases_pelo_codigo_ibge_e_nao_pelo_nome(self):
        """Nome de município é ambíguo: "Santa Luzia" existe em oito estados."""
        consulta = OverpassProvider().build_query(
            SearchQuery(ibge_code="3550308", tags={"shop": "bakery"})
        )
        assert "3550308" in consulta
        assert "name" not in consulta

    @pytest.mark.parametrize(
        "consulta",
        [
            SearchQuery(ibge_code="não-numérico", tags={"amenity": "dentist"}),
            SearchQuery(ibge_code="4113700", tags={}),
        ],
    )
    def test_recusa_busca_malformada(self, consulta):
        from apps.providers.base import ProviderError

        with pytest.raises(ProviderError):
            list(OverpassProvider().search_businesses(consulta))

    def test_descarta_elemento_sem_nome(self, monkeypatch):
        """Geometria solta não é estabelecimento."""
        fonte = OverpassProvider()
        monkeypatch.setattr(
            fonte,
            "_post",
            lambda _: {
                "elements": [
                    {"type": "node", "id": 1, "tags": {"amenity": "dentist"}},
                    {"type": "node", "id": 2, "tags": {"amenity": "dentist", "name": "Vale"}},
                ]
            },
        )

        achados = list(
            fonte.search_businesses(SearchQuery(ibge_code="4113700", tags={"amenity": "dentist"}))
        )
        assert [r.external_id for r in achados] == ["node/2"]


class TestNormalizacao:
    def test_converte_elemento_do_osm_no_dto(self):
        bruto = RawResult(
            external_id="node/1",
            payload={
                "type": "node",
                "lat": -23.31,
                "lon": -51.16,
                "tags": {
                    "name": "  Clínica São José  ",
                    "phone": "(43) 3324-1000",
                    "website": "HTTPS://WWW.Exemplo.com.br/contato",
                    "addr:street": "Avenida Higienópolis",
                    "addr:housenumber": "1200",
                    "addr:postcode": "86015-010",
                },
            },
        )

        dto = OverpassProvider().normalize_result(bruto)

        assert dto.name == "Clínica São José"
        assert dto.phones == ("+554333241000",)
        assert dto.domain == "exemplo.com.br"
        assert (dto.street, dto.number, dto.postal_code) == (
            "Avenida Higienópolis",
            "1200",
            "86015010",
        )
        assert (dto.latitude, dto.longitude) == (-23.31, -51.16)

    def test_usa_center_quando_o_elemento_e_way(self):
        bruto = RawResult(
            external_id="way/1",
            payload={"type": "way", "center": {"lat": -23.0, "lon": -51.0}, "tags": {"name": "X"}},
        )
        dto = OverpassProvider().normalize_result(bruto)
        assert (dto.latitude, dto.longitude) == (-23.0, -51.0)

    def test_telefone_repetido_nas_duas_grafias_entra_uma_vez(self):
        bruto = RawResult(
            external_id="node/1",
            payload={
                "tags": {
                    "name": "X",
                    "phone": "(43) 3324-1000",
                    "contact:phone": "43 3324-1000",
                }
            },
        )
        assert OverpassProvider().normalize_result(bruto).phones == ("+554333241000",)

    def test_cep_torto_nao_entra(self):
        bruto = RawResult(
            external_id="node/1", payload={"tags": {"name": "X", "addr:postcode": "86"}}
        )
        assert OverpassProvider().normalize_result(bruto).postal_code == "86"


class TestRetencao:
    def test_fonte_persistente_nao_expira(self, linha_mock):
        assert linha_mock.is_ephemeral is False
        assert linha_mock.expires_at() is None

    def test_fonte_efemera_expira_em_30_dias(self, db):
        """Conformidade vira schema, não disciplina (ADR-0004).

        É isto que permitiria o Google Places entrar sem violar contrato: só o `external_id`
        fica, o resto tem prazo.
        """
        from datetime import timedelta

        from django.utils import timezone

        efemera = Provider.objects.create(
            slug="efemera", name="Efêmera", retention_policy=RetentionPolicy.EPHEMERAL_30D
        )
        assert efemera.is_ephemeral
        assert efemera.expires_at() - timezone.now() > timedelta(days=29)

    def test_procedencia_de_fonte_efemera_nasce_com_prazo(self, londrina, dentistas, fonte_mock):
        from apps.providers.ingestion import ingest_city

        efemera = Provider.objects.create(
            slug="efemera", name="Efêmera", retention_policy=RetentionPolicy.EPHEMERAL_30D
        )
        ingest_city(provider=fonte_mock, provider_row=efemera, city=londrina, tags=dentistas)

        for fonte in CompanySource.objects.all():
            assert fonte.expires_at is not None
            assert fonte.is_expired is False


class TestIdempotenciaNoBanco:
    def test_banco_recusa_external_id_repetido_na_mesma_fonte(self, linha_mock, londrina):
        """É desta constraint que vem a idempotência, não de `if exists` (ADR-0003)."""
        from django.db.utils import IntegrityError

        from apps.companies.models import Company

        a = Company.objects.create(name="A")
        b = Company.objects.create(name="B")
        CompanySource.objects.create(provider=linha_mock, external_id="node/1", company=a)

        with pytest.raises(IntegrityError):
            CompanySource.objects.create(provider=linha_mock, external_id="node/1", company=b)

    def test_mesmo_external_id_em_fontes_diferentes_convive(self, linha_mock, londrina):
        from apps.companies.models import Company

        outra = Provider.objects.create(slug="outra", name="Outra")
        empresa = Company.objects.create(name="A")
        CompanySource.objects.create(provider=linha_mock, external_id="node/1", company=empresa)
        CompanySource.objects.create(provider=outra, external_id="node/1", company=empresa)

        assert empresa.sources.count() == 2


class TestRegistro:
    def test_devolve_a_fonte_com_o_limite_do_banco(self, linha_mock):
        linha_mock.rate_limit_per_second = 7
        linha_mock.save()

        fonte = get_provider(MockProvider.slug)
        assert isinstance(fonte, MockProvider)
        assert fonte.rate_limit_per_second == 7.0

    def test_recusa_fonte_desabilitada(self, linha_mock):
        """Desligar tem de valer na hora, inclusive num worker já rodando."""
        linha_mock.is_enabled = False
        linha_mock.save()

        with pytest.raises(ProviderDisabledError):
            get_provider(MockProvider.slug)

    def test_recusa_slug_desconhecido(self, db):
        from apps.providers.base import ProviderError

        with pytest.raises(ProviderError, match="desconhecida"):
            get_provider("nao-existe")

    def test_recusa_fonte_sem_linha_no_banco(self, db):
        from apps.providers.base import ProviderError

        with pytest.raises(ProviderError, match="seed_providers"):
            get_provider(MockProvider.slug)


class TestLimiteDeTaxa:
    def test_segura_a_segunda_chamada_na_mesma_janela(self):
        """A vaga é tomada com `cache.add`, que é SETNX — atômico entre processos.

        Contador por processo não serviria: cada worker do Celery acharia que tem a janela
        inteira só para si, e contra o Overpass público isso é abuso (ADR-0004).
        """
        cache.clear()

        class Fonte(BaseProvider):
            slug = "teste-limite"
            rate_limit_per_second = 1.0

            def search_businesses(self, query):  # pragma: no cover - não usado
                return []

            def normalize_result(self, raw):  # pragma: no cover - não usado
                return None

        fonte = Fonte()
        fonte.check_rate_limit()

        assert cache.get("provider:ratelimit:teste-limite") is not None


def test_mock_nao_toca_a_rede(fonte_mock, dentistas):
    """Se este teste um dia precisar de rede, a regra 5 do ADR-0003 foi quebrada."""
    achados = list(fonte_mock.search_businesses(SearchQuery(ibge_code="4113700", tags=dentistas)))
    assert len(achados) == 4
    assert all(json.dumps(r.payload) for r in achados)


def test_mock_respeita_o_filtro_de_tags(fonte_mock):
    vazio = list(
        fonte_mock.search_businesses(SearchQuery(ibge_code="4113700", tags={"shop": "bakery"}))
    )
    assert vazio == []


@override_settings(OVERPASS_MAX_BYTES=10)
def test_overpass_recusa_resposta_gigante(monkeypatch):
    """Entrada de rede sem teto carregaria o que viesse na memória do worker."""

    class RespostaFalsa:
        def read(self, n):
            return b"x" * n

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    from apps.providers import overpass
    from apps.providers.base import ProviderError

    monkeypatch.setattr(overpass.urllib.request, "urlopen", lambda *a, **k: RespostaFalsa())
    cache.clear()

    with pytest.raises(ProviderError, match="passou de 10 bytes"):
        OverpassProvider(rate_limit_per_second=1000)._post("[out:json];")
