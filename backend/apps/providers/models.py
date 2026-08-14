"""Fontes de dados: cadastro, consumo e procedência.

`Provider` é a linha de configuração da fonte; a classe que fala com ela vive em
`registry.py`. Separar assim permite ligar, desligar e afrouxar limite sem deploy.

`CompanySource` mora aqui, e não em `companies`, porque tem FK para `Provider` e a ordem de
dependência do CLAUDE.md é `companies` ← `providers`. Companies não pode importar providers.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel, TenantModel
from apps.providers.base import EPHEMERAL_TTL, RetentionPolicy


class Provider(BaseModel):
    """Uma fonte. Global: quem é o OSM não muda por organização."""

    slug = models.SlugField(_("identificador"), max_length=50, unique=True)
    name = models.CharField(_("nome"), max_length=100)
    is_enabled = models.BooleanField(_("habilitada"), default=True)
    retention_policy = models.CharField(
        _("política de retenção"),
        max_length=16,
        choices=RetentionPolicy.choices,
        default=RetentionPolicy.PERSIST,
    )
    rate_limit_per_second = models.DecimalField(
        _("requisições por segundo"), max_digits=6, decimal_places=2, default=1
    )
    daily_quota = models.PositiveIntegerField(
        _("cota diária"), null=True, blank=True, help_text=_("Vazio = sem teto.")
    )
    config = models.JSONField(_("configuração"), default=dict, blank=True)

    class Meta:
        verbose_name = _("fonte de dados")
        verbose_name_plural = _("fontes de dados")
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate_limit_per_second__gt=0),
                name="provider_rate_limit_positivo",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_ephemeral(self) -> bool:
        return self.retention_policy == RetentionPolicy.EPHEMERAL_30D

    def expires_at(self):
        """Quando o payload desta fonte deixa de poder ser guardado. `None` = nunca."""
        return timezone.now() + EPHEMERAL_TTL if self.is_ephemeral else None


class ProviderUsage(TenantModel):
    """Consumo por fonte, organização e dia.

    Existe para que o custo e o volume sejam visíveis antes da fatura ou do bloqueio — o
    Overpass público é comunitário e tem política de uso justo (ADR-0004). É `TenantModel`
    porque a conta é de quem consumiu.
    """

    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="usage")
    period = models.DateField(_("dia"), default=timezone.localdate)
    request_count = models.PositiveIntegerField(_("requisições"), default=0)
    error_count = models.PositiveIntegerField(_("erros"), default=0)
    estimated_cost = models.DecimalField(
        _("custo estimado"), max_digits=10, decimal_places=4, default=0
    )

    class Meta:
        verbose_name = _("consumo de fonte")
        verbose_name_plural = _("consumo de fontes")
        ordering = ["-period"]
        constraints = [
            # Uma linha por fonte, organização e dia — é o que torna o incremento idempotente
            # por `get_or_create` em vez de `if exists` em Python (CLAUDE.md).
            models.UniqueConstraint(
                fields=["provider", "organization", "period"],
                name="uniq_uso_por_fonte_org_dia",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider.slug} {self.period}: {self.request_count} req"


class CompanySource(BaseModel):
    """De onde veio cada empresa, e o que a fonte disse na época.

    `UniqueConstraint(provider, external_id)` é a base da idempotência (ADR-0003): reprocessar
    a mesma busca não cria empresa duplicada, porque o banco arbitra — não um `if exists`.

    `expires_at` só é preenchido para fonte efêmera. É ele que permite a uma task de expurgo
    apagar o payload sem tocar no `external_id`, que pode ficar para sempre (ADR-0004).
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="sources",
        verbose_name=_("empresa"),
    )
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="sources")
    external_id = models.CharField(_("id na fonte"), max_length=200)
    raw_payload = models.JSONField(_("payload bruto"), default=dict, blank=True)
    collected_at = models.DateTimeField(_("coletado em"), default=timezone.now)
    expires_at = models.DateTimeField(_("expira em"), null=True, blank=True)
    confidence = models.DecimalField(_("confiança"), max_digits=3, decimal_places=2, default=1)

    class Meta:
        verbose_name = _("procedência")
        verbose_name_plural = _("procedências")
        ordering = ["-collected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"], name="uniq_fonte_external_id"
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="source_confianca_entre_0_e_1",
            ),
        ]
        indexes = [models.Index(fields=["company", "provider"])]

    def __str__(self) -> str:
        return f"{self.provider.slug}:{self.external_id}"

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()
