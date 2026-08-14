"""Planejamento: transformar critérios em trabalho — ou recusar antes de gastar cota.

Recusar cedo é o ponto. Um plano impossível descoberto no meio da varredura já queimou
requisições contra um serviço comunitário (ADR-0004).
"""

import pytest
from django.test import override_settings

from apps.discovery.models import JobStatus, SearchJob
from apps.discovery.services import SearchPlanError, plan_search, resolve_cities

pytestmark = pytest.mark.django_db


class TestResolucaoDeCidades:
    def test_por_uf_pega_o_estado_inteiro(self, londrina, maringa, sao_paulo):
        cidades = resolve_cities({"uf": ["PR"]})
        assert {c.name for c in cidades} == {"Londrina", "Maringá"}

    def test_uf_e_caixa_insensivel(self, londrina):
        assert resolve_cities({"uf": ["pr"]}) == [londrina]

    def test_por_id_explicito(self, londrina, maringa):
        assert resolve_cities({"city_ids": [str(londrina.id)]}) == [londrina]

    def test_uf_e_ids_somam_sem_repetir(self, londrina, maringa, sao_paulo):
        cidades = resolve_cities({"uf": ["PR"], "city_ids": [str(londrina.id), str(sao_paulo.id)]})
        assert len(cidades) == 3
        assert len({c.id for c in cidades}) == 3


class TestParticionamento:
    def test_cria_um_job_por_cidade_categoria_fonte(
        self, criar_busca, londrina, maringa, dentistas, fonte
    ):
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])
        jobs = plan_search(busca)

        assert len(jobs) == 2
        assert {j.city for j in jobs} == {londrina, maringa}
        assert all(j.status == JobStatus.PENDING for j in jobs)

    def test_replanejar_nao_duplica(self, criar_busca):
        """Quem arbitra é a UniqueConstraint, não uma checagem em Python."""
        busca = criar_busca()
        plan_search(busca)
        plan_search(busca)

        assert SearchJob.objects.filter(search=busca).count() == 1


class TestRecusas:
    def test_sem_municipio(self, criar_busca):
        busca = criar_busca(city_ids=[], uf=["RR"])
        with pytest.raises(SearchPlanError, match="Nenhum município"):
            plan_search(busca)

    def test_sem_categoria_ativa(self, criar_busca, dentistas):
        dentistas.is_active = False
        dentistas.save()

        with pytest.raises(SearchPlanError, match="categoria ativa"):
            plan_search(criar_busca())

    def test_sem_fonte_habilitada(self, criar_busca, fonte):
        fonte.is_enabled = False
        fonte.save()

        with pytest.raises(SearchPlanError, match="fonte habilitada"):
            plan_search(criar_busca())

    def test_categoria_sem_traducao_para_a_fonte(self, criar_busca, sem_mapeamento):
        """O provider não saberia o que perguntar — `provider_mapping` é o que traduz."""
        busca = criar_busca(category_ids=[str(sem_mapeamento.id)])

        with pytest.raises(SearchPlanError, match="mapeamento"):
            plan_search(busca)

    @override_settings(DISCOVERY_MAX_JOBS_PER_SEARCH=1)
    def test_recusa_plano_acima_do_teto_sem_criar_nada(self, criar_busca, londrina, maringa):
        """Varrer o Brasil contra o Overpass público é abuso, não ambição (ADR-0004).

        A recusa vem antes de qualquer INSERT: nada de meia busca no banco.
        """
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])

        with pytest.raises(SearchPlanError, match="acima do teto"):
            plan_search(busca)

        assert SearchJob.objects.count() == 0
