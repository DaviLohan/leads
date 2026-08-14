"""Planejar e executar uma busca.

Duas responsabilidades separadas de propósito:

- **planejar** (`plan_search`) resolve os critérios em N `SearchJob` e não fala com a rede;
- **executar** (`run_job`) pega um job e o roda contra a fonte.

Separar permite ver quanto trabalho uma busca vai dar **antes** de disparar qualquer
requisição — e recusar a que for grande demais, em vez de descobrir isso já abusando de um
serviço comunitário (ADR-0004).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.companies.models import Category
from apps.discovery.models import (
    JOB_TERMINAL,
    JobStatus,
    Search,
    SearchJob,
    SearchResult,
    SearchStatus,
)
from apps.geography.models import City
from apps.providers.ingestion import ingest_city
from apps.providers.models import Provider
from apps.providers.registry import get_provider

logger = logging.getLogger(__name__)


class SearchPlanError(ValueError):
    """Critérios que não dá para transformar em trabalho."""


def resolve_cities(criteria: dict) -> list[City]:
    """Traduz os critérios em municípios.

    Aceita `city_ids` (escolha explícita) e/ou `uf` (o estado inteiro). Os dois juntos se
    somam, sem repetir.
    """
    consulta = City.objects.none()

    if ufs := criteria.get("uf"):
        consulta = consulta | City.objects.filter(state__uf__in=[u.upper() for u in ufs])
    if ids := criteria.get("city_ids"):
        consulta = consulta | City.objects.filter(id__in=ids)

    return list(consulta.select_related("state").distinct().order_by("name"))


def plan_search(search: Search) -> list[SearchJob]:
    """Cria os jobs de uma busca: um por cidade x categoria x fonte.

    Recusa antes de criar qualquer coisa se o plano passar do teto. Varrer o Brasil inteiro
    contra o Overpass público é abuso, não ambição (ADR-0004) — e o limite existe para
    transformar isso em erro claro na criação, e não em bloqueio pela fonte no meio da noite.
    """
    criteria = search.criteria or {}

    cidades = resolve_cities(criteria)
    if not cidades:
        raise SearchPlanError("Nenhum município corresponde aos critérios.")

    categorias = list(
        Category.objects.filter(id__in=criteria.get("category_ids", []), is_active=True)
    )
    if not categorias:
        raise SearchPlanError("Nenhuma categoria ativa foi informada.")

    slugs = criteria.get("provider_slugs") or []
    fontes = list(Provider.objects.filter(slug__in=slugs, is_enabled=True))
    if not fontes:
        raise SearchPlanError("Nenhuma fonte habilitada foi informada.")

    # Categoria sem tradução para a fonte não vira trabalho: o provider não saberia o que
    # perguntar. É `Category.provider_mapping` que evita categoria hardcoded no provider.
    combinacoes = [
        (cidade, categoria, fonte)
        for fonte in fontes
        for categoria in categorias
        if categoria.provider_mapping.get(fonte.slug)
        for cidade in cidades
    ]
    if not combinacoes:
        raise SearchPlanError(
            "Nenhuma das categorias tem mapeamento para as fontes escolhidas "
            f"({', '.join(f.slug for f in fontes)})."
        )

    teto = settings.DISCOVERY_MAX_JOBS_PER_SEARCH
    if len(combinacoes) > teto:
        raise SearchPlanError(
            f"Esta busca geraria {len(combinacoes)} jobs, acima do teto de {teto}. "
            "Recorte por município ou categoria."
        )

    with transaction.atomic():
        jobs = SearchJob.objects.bulk_create(
            [
                SearchJob(search=search, city=cidade, category=categoria, provider=fonte)
                for cidade, categoria, fonte in combinacoes
            ],
            # Replanejar uma busca não pode duplicar trabalho; quem arbitra é a
            # UniqueConstraint, não uma checagem em Python.
            ignore_conflicts=True,
        )

    logger.info(
        "Busca planejada",
        extra={"search": str(search.pk), "jobs": len(jobs), "cidades": len(cidades)},
    )
    return list(search.jobs.all())


def claim_job(job_id) -> SearchJob | None:
    """Marca o job como executando, se ninguém o pegou antes.

    O `select_for_update` é o que impede dois workers de varrerem o mesmo município ao mesmo
    tempo — o que gastaria cota em dobro e produziria dois `SearchResult` para o mesmo
    resultado. Quem arbitra é o banco; um `if status == RUNNING` em Python teria corrida.

    Devolve `None` quando o job já está rodando ou já terminou.
    """
    with transaction.atomic():
        job = SearchJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status in (JobStatus.RUNNING, *JOB_TERMINAL):
            return None

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = job.started_at or timezone.now()
        job.last_error = ""
        job.save(update_fields=["status", "attempts", "started_at", "last_error", "updated_at"])
        return job


def run_job(job: SearchJob) -> SearchJob:
    """Executa um job já reivindicado. Erro sobe: quem decide repetir é a task."""
    fonte = get_provider(job.provider.slug)
    tags = job.category.provider_mapping[job.provider.slug]

    relatorio = ingest_city(
        provider=fonte,
        provider_row=job.provider,
        city=job.city,
        tags=tags,
        organization=job.search.organization,
    )

    with transaction.atomic():
        _gravar_resultados(job, relatorio)

        job.found_count = relatorio.total
        job.new_count = relatorio.created
        job.duplicate_count = relatorio.updated
        job.review_count = relatorio.review
        job.error_count = relatorio.skipped
        job.api_calls += 1
        job.status = JobStatus.COMPLETED
        job.finished_at = timezone.now()
        job.save()

    refresh_search_status(job.search)
    return job


def _gravar_resultados(job: SearchJob, relatorio) -> None:
    """Um `SearchResult` por resultado. Reexecutar atualiza, não duplica."""
    for registro in relatorio.records:
        SearchResult.objects.update_or_create(
            search_job=job,
            external_id=registro.external_id,
            defaults={
                "company_id": registro.company_id,
                "match_type": registro.match_type,
                "normalized_payload": registro.payload,
                "matched_score": round(registro.score, 3),
            },
        )


def fail_job(job: SearchJob, erro: Exception, *, definitivo: bool) -> None:
    """Registra a falha. `definitivo` significa que não haverá nova tentativa."""
    job.status = JobStatus.FAILED if definitivo else JobStatus.PENDING
    # A mensagem é truncada: um traceback de 40 KB por job inviabiliza a tela de progresso,
    # e o traceback inteiro já está no log estruturado.
    job.last_error = f"{type(erro).__name__}: {erro}"[:2000]
    if definitivo:
        job.finished_at = timezone.now()
    job.save(update_fields=["status", "last_error", "finished_at", "updated_at"])

    if definitivo:
        refresh_search_status(job.search)


def refresh_search_status(search: Search) -> Search:
    """Recalcula a situação da busca a partir dos jobs.

    Deriva em vez de acumular: contador incrementado por worker paralelo diverge, e a
    divergência aparece como busca eternamente "em andamento" com tudo pronto.
    """
    from django.db.models import Count, Q

    totais = search.jobs.aggregate(
        total=Count("id"),
        prontos=Count("id", filter=Q(status__in=JOB_TERMINAL)),
        falhos=Count("id", filter=Q(status=JobStatus.FAILED)),
        rodando=Count("id", filter=Q(status=JobStatus.RUNNING)),
    )

    if not totais["total"]:
        novo = SearchStatus.PENDING
    elif totais["prontos"] < totais["total"]:
        novo = (
            SearchStatus.RUNNING if totais["rodando"] or totais["prontos"] else SearchStatus.PENDING
        )
    elif totais["falhos"] == totais["total"]:
        novo = SearchStatus.FAILED
    elif totais["falhos"]:
        novo = SearchStatus.PARTIALLY_COMPLETED
    else:
        novo = SearchStatus.COMPLETED

    mudou = ["status", "updated_at"]
    search.status = novo
    if novo == SearchStatus.RUNNING and search.started_at is None:
        search.started_at = timezone.now()
        mudou.append("started_at")
    if novo in (SearchStatus.COMPLETED, SearchStatus.PARTIALLY_COMPLETED, SearchStatus.FAILED):
        search.finished_at = search.finished_at or timezone.now()
        mudou.append("finished_at")

    search.save(update_fields=mudou)
    return search


def cancel_search(search: Search) -> int:
    """Cancela os jobs que ainda não começaram. O que já está rodando termina.

    Matar uma task no meio deixaria empresa gravada sem `SearchResult` correspondente — e a
    varredura já pagou o custo da chamada à fonte de qualquer jeito.
    """
    cancelados = search.jobs.exclude(status__in=(JobStatus.RUNNING, *JOB_TERMINAL)).update(
        status=JobStatus.CANCELLED, finished_at=timezone.now()
    )
    search.refresh_from_db()
    if not search.jobs.filter(status=JobStatus.RUNNING).exists():
        search.status = SearchStatus.CANCELLED
        search.finished_at = timezone.now()
        search.save(update_fields=["status", "finished_at", "updated_at"])
    return cancelados
