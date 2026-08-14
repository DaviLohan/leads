"""Descoberta: a busca que o usuário pede e o trabalho que ela gera.

Uma `Search` é a intenção ("dentistas em Londrina e Maringá, pelo OSM"). O particionamento
a quebra em N `SearchJob`, um por **cidade x categoria x fonte** — a menor unidade que uma
task consegue executar, repetir e reportar sozinha.

Por que a unidade é essa: se um município falhar, só ele volta para a fila. Uma busca única
e monolítica obrigaria a refazer o Paraná inteiro por causa de um 504 em Cambé.

Tudo aqui é do tenant (ADR-0007). Busca é dado comercial: o que uma organização procurou, e
quando, não é da conta das outras. `SearchJob` e `SearchResult` herdam o escopo pela
`Search` — repetir a FK de organização neles seria desnormalizar sem ganho, e criar a chance
de os dois discordarem.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.companies.dedup import MatchType
from apps.core.models import BaseModel, TenantModel


class SearchStatus(models.TextChoices):
    PENDING = "PENDING", _("Aguardando")
    RUNNING = "RUNNING", _("Em andamento")
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED", _("Concluída com falhas")
    COMPLETED = "COMPLETED", _("Concluída")
    FAILED = "FAILED", _("Falhou")
    CANCELLED = "CANCELLED", _("Cancelada")


class JobStatus(models.TextChoices):
    PENDING = "PENDING", _("Aguardando")
    SCHEDULED = "SCHEDULED", _("Enfileirado")
    RUNNING = "RUNNING", _("Executando")
    COMPLETED = "COMPLETED", _("Concluído")
    FAILED = "FAILED", _("Falhou")
    CANCELLED = "CANCELLED", _("Cancelado")


# Situações em que o job já terminou e não deve ser reexecutado.
JOB_TERMINAL = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class Search(TenantModel):
    """O que a organização pediu para procurar."""

    name = models.CharField(_("nome"), max_length=150)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="searches",
        verbose_name=_("criada por"),
    )
    # UFs, cidades, categorias e fontes escolhidas. Fica em JSON porque é o pedido como o
    # usuário fez — o que virou trabalho está nos `SearchJob`, em coluna e com FK.
    criteria = models.JSONField(_("critérios"), default=dict, blank=True)
    status = models.CharField(
        _("situação"), max_length=24, choices=SearchStatus.choices, default=SearchStatus.PENDING
    )
    started_at = models.DateTimeField(_("iniciada em"), null=True, blank=True)
    finished_at = models.DateTimeField(_("concluída em"), null=True, blank=True)

    class Meta:
        verbose_name = _("busca")
        verbose_name_plural = _("buscas")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return self.name

    @property
    def progress(self) -> int:
        """Percentual concluído, calculado a partir dos jobs — nunca guardado.

        Guardar o percentual criaria duas verdades, e a errada seria justamente a que a tela
        mostra.

        Usa as anotações `job_count` e `jobs_done` quando quem consultou as trouxe (é o que
        a listagem da API faz), e só consulta o banco quando elas não existem — admin, shell,
        objeto solto. Uma fórmula só, dois caminhos de dado.
        """
        total = getattr(self, "job_count", None)
        prontos = getattr(self, "jobs_done", None)

        if total is None or prontos is None:
            totais = self.jobs.aggregate(
                total=models.Count("id"),
                prontos=models.Count("id", filter=models.Q(status__in=JOB_TERMINAL)),
            )
            total, prontos = totais["total"], totais["prontos"]

        return round(100 * prontos / total) if total else 0


class SearchJobQuerySet(models.QuerySet):
    def for_organization(self, organization) -> SearchJobQuerySet:
        """O escopo vem pela busca. Assinatura igual à de `TenantQuerySet` de propósito:
        é o que permite ao `TenantViewSet` impor o isolamento sem saber a diferença."""
        if organization is None:
            return self.none()
        return self.filter(search__organization=organization)


class SearchJob(BaseModel):
    """Uma unidade de trabalho: um município, uma categoria, uma fonte."""

    search = models.ForeignKey(
        Search, on_delete=models.CASCADE, related_name="jobs", verbose_name=_("busca")
    )
    city = models.ForeignKey("geography.City", on_delete=models.PROTECT, related_name="search_jobs")
    category = models.ForeignKey(
        "companies.Category", on_delete=models.PROTECT, related_name="search_jobs"
    )
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.PROTECT, related_name="search_jobs"
    )

    status = models.CharField(
        _("situação"), max_length=16, choices=JobStatus.choices, default=JobStatus.PENDING
    )
    found_count = models.PositiveIntegerField(_("encontradas"), default=0)
    new_count = models.PositiveIntegerField(_("novas"), default=0)
    duplicate_count = models.PositiveIntegerField(_("já conhecidas"), default=0)
    review_count = models.PositiveIntegerField(_("para revisão"), default=0)
    error_count = models.PositiveIntegerField(_("erros"), default=0)
    api_calls = models.PositiveIntegerField(_("chamadas à fonte"), default=0)
    attempts = models.PositiveIntegerField(_("tentativas"), default=0)
    last_error = models.TextField(_("último erro"), blank=True)
    started_at = models.DateTimeField(_("iniciado em"), null=True, blank=True)
    finished_at = models.DateTimeField(_("concluído em"), null=True, blank=True)

    objects = SearchJobQuerySet.as_manager()

    class Meta:
        verbose_name = _("job de busca")
        verbose_name_plural = _("jobs de busca")
        ordering = ["city__name"]
        constraints = [
            # A mesma combinação duas vezes na mesma busca é trabalho repetido contra uma
            # fonte externa — desperdício de cota e de tempo. O banco recusa.
            models.UniqueConstraint(
                fields=["search", "city", "category", "provider"],
                name="uniq_job_por_busca_cidade_categoria_fonte",
            ),
        ]
        indexes = [models.Index(fields=["search", "status"])]

    def __str__(self) -> str:
        return f"{self.city} / {self.category} / {self.provider.slug}"

    @property
    def is_terminal(self) -> bool:
        return self.status in JOB_TERMINAL


class SearchResult(BaseModel):
    """O que um job achou, e como aquilo foi resolvido.

    Guarda a decisão da deduplicação **por resultado**: é o que permite auditar uma fusão
    depois, e é onde a revisão humana de `POSSIBLE` vai buscar sua fila de trabalho.
    """

    search_job = models.ForeignKey(
        SearchJob, on_delete=models.CASCADE, related_name="results", verbose_name=_("job")
    )
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_results",
        verbose_name=_("empresa"),
    )
    external_id = models.CharField(_("id na fonte"), max_length=200)
    match_type = models.CharField(_("correspondência"), max_length=16, choices=MatchType.choices)
    # Só o que a normalização produziu. O payload cru fica em `CompanySource`, uma vez por
    # fonte — repeti-lo aqui multiplicaria o mesmo JSON por cada busca que reencontrasse a
    # empresa.
    normalized_payload = models.JSONField(_("dados normalizados"), default=dict, blank=True)
    matched_score = models.DecimalField(
        _("similaridade"), max_digits=4, decimal_places=3, null=True, blank=True
    )

    class Meta:
        verbose_name = _("resultado")
        verbose_name_plural = _("resultados")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["search_job", "external_id"], name="uniq_resultado_por_job_external_id"
            ),
        ]
        indexes = [models.Index(fields=["search_job", "match_type"])]

    def __str__(self) -> str:
        return f"{self.external_id} → {self.match_type}"
