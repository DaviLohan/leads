"""Diagnóstico de presença digital.

Global (ADR-0007): o que o site de uma empresa tem ou não tem é fato público sobre ela, igual
para toda organização. Fosse por tenant, cada uma varreria o mesmo site para chegar ao mesmo
resultado — e o dono do site levaria a varredura em dobro.

O que este app **não** decide: se um sinal ausente vale uma venda. Isso é a Etapa 10
(Opportunity Engine). Aqui só se registra o que foi observado, com evidência.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class WebsiteScan(BaseModel):
    """Uma visita ao site de uma empresa, e o que ela revelou."""

    class Status(models.TextChoices):
        OK = "OK", _("Analisado")
        UNREACHABLE = "UNREACHABLE", _("Fora do ar ou inalcançável")
        # Separado de UNREACHABLE de propósito: o guard ter recusado a URL é evento de
        # segurança, não indisponibilidade. Confundir os dois esconderia uma tentativa de
        # SSRF atrás de "o site está fora do ar".
        BLOCKED = "BLOCKED", _("Recusado pelo guard de SSRF")
        ERROR = "ERROR", _("Erro na análise")

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="scans",
        verbose_name=_("empresa"),
    )
    website = models.ForeignKey(
        "companies.CompanyWebsite",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scans",
        verbose_name=_("site"),
    )

    status = models.CharField(_("situação"), max_length=16, choices=Status.choices)
    final_url = models.URLField(_("URL final"), max_length=500, blank=True)
    http_status = models.PositiveSmallIntegerField(_("HTTP"), null=True, blank=True)
    is_https = models.BooleanField(_("HTTPS"), default=False)
    has_valid_cert = models.BooleanField(_("certificado válido"), default=False)
    response_time_ms = models.PositiveIntegerField(
        _("tempo de resposta (ms)"), null=True, blank=True
    )
    redirect_count = models.PositiveSmallIntegerField(_("redirects"), default=0)

    title = models.CharField(_("título"), max_length=300, blank=True)
    meta_description = models.CharField(_("descrição"), max_length=500, blank=True)

    # Os sinais que a Etapa 10 vai ler para decidir oportunidade.
    has_viewport = models.BooleanField(_("responsivo"), default=False)
    has_contact_form = models.BooleanField(_("formulário de contato"), default=False)
    has_whatsapp = models.BooleanField(_("WhatsApp"), default=False)
    has_booking = models.BooleanField(_("agendamento"), default=False)
    has_cart = models.BooleanField(_("carrinho"), default=False)

    # O que ainda não vale coluna: campo novo de sinal entra aqui antes de virar schema.
    signals = models.JSONField(_("outros sinais"), default=dict, blank=True)
    error_detail = models.TextField(_("detalhe do erro"), blank=True)
    scanned_at = models.DateTimeField(_("analisado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("análise de site")
        verbose_name_plural = _("análises de site")
        ordering = ["-scanned_at"]
        indexes = [
            models.Index(fields=["company", "-scanned_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} — {self.get_status_display()}"


class WebsiteFinding(BaseModel):
    """Um achado da análise, com evidência.

    Achado é observação, não julgamento: "não tem HTTPS" é fato verificável. Quanto isso vale
    em oportunidade de venda é decisão da Etapa 10, parametrizada no banco (ADR-0008).
    """

    class Code(models.TextChoices):
        NO_HTTPS = "NO_HTTPS", _("Site sem HTTPS")
        INVALID_CERT = "INVALID_CERT", _("Certificado inválido")
        NO_VIEWPORT = "NO_VIEWPORT", _("Não adaptado para celular")
        SLOW_RESPONSE = "SLOW_RESPONSE", _("Resposta lenta")
        NO_CONTACT_CHANNEL = "NO_CONTACT_CHANNEL", _("Sem formulário nem WhatsApp")
        NO_BOOKING = "NO_BOOKING", _("Sem agendamento online")
        SITE_OFFLINE = "SITE_OFFLINE", _("Site fora do ar")
        EXCESSIVE_REDIRECTS = "EXCESSIVE_REDIRECTS", _("Redirects em excesso")
        BLOCKED_TARGET = "BLOCKED_TARGET", _("Destino recusado pelo guard de SSRF")

    class Severity(models.TextChoices):
        INFO = "INFO", _("Informativo")
        LOW = "LOW", _("Baixa")
        MEDIUM = "MEDIUM", _("Média")
        HIGH = "HIGH", _("Alta")

    scan = models.ForeignKey(
        WebsiteScan, on_delete=models.CASCADE, related_name="findings", verbose_name=_("análise")
    )
    code = models.CharField(_("código"), max_length=32, choices=Code.choices)
    severity = models.CharField(
        _("severidade"), max_length=8, choices=Severity.choices, default=Severity.MEDIUM
    )
    detail = models.TextField(_("detalhe"), blank=True)
    evidence = models.JSONField(_("evidência"), default=dict, blank=True)

    class Meta:
        verbose_name = _("achado")
        verbose_name_plural = _("achados")
        ordering = ["severity", "code"]
        constraints = [
            # O mesmo achado duas vezes na mesma análise é ruído: a tela mostraria "sem
            # HTTPS" repetido, e a Etapa 10 contaria o mesmo problema mais de uma vez.
            models.UniqueConstraint(fields=["scan", "code"], name="uniq_achado_por_analise"),
        ]

    def __str__(self) -> str:
        return f"{self.get_code_display()} ({self.severity})"


class OpportunityType(BaseModel):
    """Um tipo de oportunidade de venda, com o predicado que a detecta (ADR-0008).

    `rule_code` referencia um predicado registrado em `apps.analysis.rules`. O banco decide
    se está ativo, com que confiança e com quais parâmetros — o código decide **como**
    avaliar. Código desconhecido é ignorado com aviso, nunca quebra o motor.
    """

    code = models.SlugField(_("código"), max_length=60, unique=True)
    name = models.CharField(_("nome"), max_length=120)
    description = models.TextField(_("descrição"), blank=True)
    rule_code = models.CharField(_("regra"), max_length=60)
    rule_params = models.JSONField(_("parâmetros da regra"), default=dict, blank=True)
    # Restringe o tipo a certas categorias. Vazio = vale para qualquer uma. É o que faz
    # "agendamento" valer para clínica e não para oficina, sem `if` no motor.
    category_slugs = models.JSONField(_("categorias"), default=list, blank=True)
    base_confidence = models.DecimalField(_("confiança"), max_digits=3, decimal_places=2, default=1)
    is_active = models.BooleanField(_("ativo"), default=True)

    class Meta:
        verbose_name = _("tipo de oportunidade")
        verbose_name_plural = _("tipos de oportunidade")
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(base_confidence__gte=0, base_confidence__lte=1),
                name="tipo_confianca_entre_0_e_1",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Opportunity(BaseModel):
    """Uma oportunidade detectada para uma empresa.

    Global, como o resto da análise: "esta clínica não tem agendamento online" é fato sobre
    a empresa, não sobre quem a prospecta. O que é do tenant é o `Lead` (Etapa 12).

    Não é apagada quando some: vira `RESOLVED` com data. Empresa que finalmente pôs
    agendamento no ar é informação comercial — sai do radar, fica no histórico.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", _("Aberta")
        RESOLVED = "RESOLVED", _("Resolvida")
        DISMISSED = "DISMISSED", _("Descartada")

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="opportunities",
        verbose_name=_("empresa"),
    )
    type = models.ForeignKey(
        OpportunityType,
        on_delete=models.PROTECT,
        related_name="opportunities",
        verbose_name=_("tipo"),
    )
    status = models.CharField(
        _("situação"), max_length=16, choices=Status.choices, default=Status.OPEN
    )
    confidence = models.DecimalField(_("confiança"), max_digits=3, decimal_places=2, default=1)
    # O que sustentava a conclusão no momento da deteção. Sem isto, "detectamos que não tem
    # agendamento" é afirmação sem lastro — e quem for vender não sabe o que dizer.
    evidence = models.JSONField(_("evidência"), default=dict, blank=True)
    detected_at = models.DateTimeField(_("detectada em"), auto_now_add=True)
    resolved_at = models.DateTimeField(_("resolvida em"), null=True, blank=True)

    class Meta:
        verbose_name = _("oportunidade")
        verbose_name_plural = _("oportunidades")
        ordering = ["-detected_at"]
        constraints = [
            # Uma oportunidade por empresa e tipo: reavaliar atualiza a existente em vez de
            # empilhar duplicatas a cada varredura.
            models.UniqueConstraint(
                fields=["company", "type"], name="uniq_oportunidade_por_empresa_tipo"
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="oportunidade_confianca_entre_0_e_1",
            ),
        ]
        indexes = [models.Index(fields=["status", "-detected_at"])]

    def __str__(self) -> str:
        return f"{self.company.name} — {self.type.name}"
