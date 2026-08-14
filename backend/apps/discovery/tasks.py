"""Tasks de descoberta.

Casca fina (CLAUDE.md): a task recebe **IDs**, não objetos, e delega a `services`. Passar
um model serializado pelo broker guardaria um retrato velho do banco — e a task rodaria com
dado que já mudou.

Idempotência é do `claim_job`, que arbitra no banco: a mesma task entregue duas vezes pelo
broker (acontece, `acks_late` garante isso) executa uma vez só.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.discovery.models import JobStatus, Search, SearchJob
from apps.discovery.services import claim_job, fail_job, plan_search, run_job
from apps.providers.base import ProviderError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    # Só falha de fonte é repetida. `ValueError` de payload torto repetiria para sempre com
    # o mesmo resultado, e o CLAUDE.md proíbe retry infinito.
    autoretry_for=(ProviderError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=settings.DISCOVERY_JOB_MAX_RETRIES,
    ignore_result=True,
)
def run_search_job(self, job_id: str) -> str:
    """Varre um município. Reentregar não duplica: `claim_job` arbitra no banco."""
    job = claim_job(job_id)
    if job is None:
        logger.info("Job já reivindicado ou encerrado", extra={"job": job_id})
        return "ignorado"

    try:
        run_job(job)
    except ProviderError as exc:
        # A fonte falhou. Volta para PENDING e o Celery reagenda com backoff — a menos que
        # esta já tenha sido a última tentativa.
        ultima = self.request.retries >= self.max_retries
        fail_job(job, exc, definitivo=ultima)
        raise
    except Exception as exc:
        # Não é a fonte: é o nosso lado. Repetir daria o mesmo erro (CLAUDE.md).
        logger.exception("Job falhou definitivamente", extra={"job": job_id})
        fail_job(job, exc, definitivo=True)
        raise

    return "concluído"


@shared_task(ignore_result=True)
def dispatch_search(search_id: str) -> int:
    """Planeja a busca e enfileira um job por município.

    Enfileira só o que ainda não terminou: redisparar uma busca parcialmente concluída
    retoma de onde parou, em vez de refazer o que já custou chamada à fonte.
    """
    search = Search.objects.get(pk=search_id)
    plan_search(search)

    # A lista é materializada antes de enfileirar: com `CELERY_TASK_ALWAYS_EAGER` (testes) o
    # `.delay()` roda na hora, e um queryset preguiçoso reavaliado depois já veria os jobs
    # concluídos — devolvendo zero para uma busca que acabou de rodar inteira.
    ids = list(search.jobs.filter(status=JobStatus.PENDING).values_list("id", flat=True))

    # SCHEDULED antes de enfileirar, e não depois: com execução síncrona, marcar depois
    # sobrescreveria COMPLETED de volta para "na fila".
    SearchJob.objects.filter(id__in=ids).update(status=JobStatus.SCHEDULED)

    for job_id in ids:
        run_search_job.delay(str(job_id))

    logger.info("Busca disparada", extra={"search": search_id, "jobs": len(ids)})
    return len(ids)
