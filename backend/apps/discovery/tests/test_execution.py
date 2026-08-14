"""Execução: reivindicar, rodar, contar e falhar direito.

As tasks rodam síncronas nos testes (`CELERY_TASK_ALWAYS_EAGER`), então o que se exercita
aqui é a lógica de verdade — não um dublê de fila.
"""

import pytest

from apps.companies.models import Company
from apps.discovery.models import JobStatus, SearchJob, SearchResult, SearchStatus
from apps.discovery.services import (
    cancel_search,
    claim_job,
    fail_job,
    plan_search,
    refresh_search_status,
    run_job,
)
from apps.discovery.tasks import dispatch_search, run_search_job
from apps.providers.base import ProviderError

pytestmark = pytest.mark.django_db


class TestReivindicacao:
    def test_marca_como_executando(self, criar_busca):
        job = plan_search(criar_busca())[0]

        reivindicado = claim_job(job.pk)

        assert reivindicado.status == JobStatus.RUNNING
        assert reivindicado.attempts == 1
        assert reivindicado.started_at is not None

    def test_segundo_worker_nao_pega_o_mesmo_job(self, criar_busca):
        """Sem isso, dois workers varreriam o mesmo município e gastariam cota em dobro."""
        job = plan_search(criar_busca())[0]

        assert claim_job(job.pk) is not None
        assert claim_job(job.pk) is None

    def test_job_ja_concluido_nao_e_reivindicado(self, criar_busca):
        job = plan_search(criar_busca())[0]
        SearchJob.objects.filter(pk=job.pk).update(status=JobStatus.COMPLETED)

        assert claim_job(job.pk) is None

    def test_job_inexistente_devolve_none(self, db):
        import uuid

        assert claim_job(uuid.uuid4()) is None


class TestExecucao:
    def test_roda_e_contabiliza(self, criar_busca):
        job = claim_job(plan_search(criar_busca())[0].pk)

        run_job(job)

        job.refresh_from_db()
        assert job.status == JobStatus.COMPLETED
        assert job.new_count == 4  # o mock tem 5 elementos; um não tem nome
        assert job.found_count == 4
        assert job.api_calls == 1
        assert job.finished_at is not None
        assert Company.objects.count() == 4

    def test_grava_um_resultado_por_empresa(self, criar_busca):
        job = claim_job(plan_search(criar_busca())[0].pk)
        run_job(job)

        resultados = SearchResult.objects.filter(search_job=job)
        assert resultados.count() == 4
        assert all(r.company_id for r in resultados)
        assert all(r.normalized_payload["name"] for r in resultados)

    def test_reexecutar_atualiza_o_resultado_em_vez_de_duplicar(self, criar_busca):
        job = plan_search(criar_busca())[0]
        run_job(claim_job(job.pk))

        SearchJob.objects.filter(pk=job.pk).update(status=JobStatus.PENDING)
        run_job(claim_job(job.pk))

        assert SearchResult.objects.filter(search_job_id=job.pk).count() == 4
        assert Company.objects.count() == 4

    def test_possible_vira_resultado_para_revisao_sem_criar_empresa(self, criar_busca, londrina):
        """A fila de revisão humana é `SearchResult` com `match_type=POSSIBLE`."""
        from apps.companies.dedup import MatchType
        from apps.companies.models import CompanyAddress

        parecida = Company.objects.create(name="Clínica Odontológica São Pedro")
        CompanyAddress.objects.create(company=parecida, city=londrina)

        job = claim_job(plan_search(criar_busca())[0].pk)
        run_job(job)

        pendente = SearchResult.objects.get(match_type=MatchType.POSSIBLE)
        assert pendente.company == parecida
        assert pendente.matched_score > 0.6
        assert not Company.objects.filter(name="Clínica Odontológica São José").exists()


class TestSituacaoDaBusca:
    def test_derivada_dos_jobs(self, criar_busca, londrina, maringa):
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])
        jobs = plan_search(busca)

        assert refresh_search_status(busca).status == SearchStatus.PENDING

        SearchJob.objects.filter(pk=jobs[0].pk).update(status=JobStatus.COMPLETED)
        assert refresh_search_status(busca).status == SearchStatus.RUNNING
        assert busca.progress == 50

        SearchJob.objects.filter(pk=jobs[1].pk).update(status=JobStatus.COMPLETED)
        assert refresh_search_status(busca).status == SearchStatus.COMPLETED
        assert busca.progress == 100

    def test_falha_parcial_e_visivel(self, criar_busca, londrina, maringa):
        """Concluída com falhas não é "concluída": esconder isso mente sobre a cobertura."""
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])
        jobs = plan_search(busca)

        SearchJob.objects.filter(pk=jobs[0].pk).update(status=JobStatus.COMPLETED)
        SearchJob.objects.filter(pk=jobs[1].pk).update(status=JobStatus.FAILED)

        assert refresh_search_status(busca).status == SearchStatus.PARTIALLY_COMPLETED

    def test_todos_falhando_e_falha(self, criar_busca):
        busca = criar_busca()
        jobs = plan_search(busca)
        SearchJob.objects.filter(pk=jobs[0].pk).update(status=JobStatus.FAILED)

        assert refresh_search_status(busca).status == SearchStatus.FAILED

    def test_progresso_de_busca_sem_job_e_zero(self, criar_busca):
        assert criar_busca().progress == 0


class TestFalhas:
    def test_falha_recuperavel_volta_para_a_fila(self, criar_busca):
        job = claim_job(plan_search(criar_busca())[0].pk)

        fail_job(job, ProviderError("504"), definitivo=False)

        job.refresh_from_db()
        assert job.status == JobStatus.PENDING
        assert "ProviderError: 504" in job.last_error
        assert job.finished_at is None

    def test_falha_definitiva_encerra_o_job(self, criar_busca):
        job = claim_job(plan_search(criar_busca())[0].pk)

        fail_job(job, ProviderError("morreu"), definitivo=True)

        job.refresh_from_db()
        assert job.status == JobStatus.FAILED
        assert job.finished_at is not None

    def test_erro_gigante_e_truncado(self, criar_busca):
        """Traceback de 40 KB por job inviabiliza a tela de progresso."""
        job = claim_job(plan_search(criar_busca())[0].pk)

        fail_job(job, ProviderError("x" * 5000), definitivo=True)

        job.refresh_from_db()
        assert len(job.last_error) <= 2000

    def test_task_registra_falha_nossa_como_definitiva(self, criar_busca, monkeypatch):
        """Erro do nosso lado repetiria com o mesmo resultado — não é para repetir."""
        from apps.discovery import tasks

        monkeypatch.setattr(
            tasks, "run_job", lambda job: (_ for _ in ()).throw(ValueError("bug nosso"))
        )
        job = plan_search(criar_busca())[0]

        with pytest.raises(ValueError):
            run_search_job(str(job.pk))

        job.refresh_from_db()
        assert job.status == JobStatus.FAILED
        assert "bug nosso" in job.last_error

    def test_task_reentregue_nao_executa_duas_vezes(self, criar_busca):
        """`acks_late` faz o broker reentregar; `claim_job` é quem impede o trabalho dobrado."""
        job = plan_search(criar_busca())[0]

        assert run_search_job(str(job.pk)) == "concluído"
        assert run_search_job(str(job.pk)) == "ignorado"
        assert Company.objects.count() == 4


class TestDisparo:
    def test_planeja_e_executa_tudo(self, criar_busca, londrina, maringa):
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])

        assert dispatch_search(str(busca.pk)) == 2

        busca.refresh_from_db()
        assert busca.status == SearchStatus.COMPLETED
        assert busca.progress == 100
        assert busca.jobs.filter(status=JobStatus.COMPLETED).count() == 2

    def test_redisparar_retoma_de_onde_parou(self, criar_busca, londrina, maringa):
        """Refazer o que já custou chamada à fonte é desperdício de cota."""
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])
        jobs = plan_search(busca)
        SearchJob.objects.filter(pk=jobs[0].pk).update(status=JobStatus.COMPLETED)

        assert dispatch_search(str(busca.pk)) == 1


class TestCancelamento:
    def test_cancela_o_que_nao_comecou(self, criar_busca, londrina, maringa):
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])
        plan_search(busca)

        assert cancel_search(busca) == 2

        busca.refresh_from_db()
        assert busca.status == SearchStatus.CANCELLED
        assert busca.jobs.filter(status=JobStatus.CANCELLED).count() == 2

    def test_nao_mexe_no_que_ja_terminou(self, criar_busca, londrina, maringa):
        busca = criar_busca(city_ids=[str(londrina.id), str(maringa.id)])
        jobs = plan_search(busca)
        SearchJob.objects.filter(pk=jobs[0].pk).update(status=JobStatus.COMPLETED)

        assert cancel_search(busca) == 1
        assert busca.jobs.filter(status=JobStatus.COMPLETED).count() == 1
