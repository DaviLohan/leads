"""Empresas: a entidade permanente do sistema.

Princípio fundamental do produto (PROJECT_PLAN §1): **empresa é entidade permanente**, não
um "lead descartável". Ela aparece em várias buscas, tem várias fontes, telefones, sites e
diagnósticos, e muda de situação com o tempo. Redescobrir não duplica — daí os campos
`discovered_at` / `last_seen_at` e a normalização em coluna própria.

Tudo aqui é **global**, não do tenant (ADR-0007): dado público sobre empresa é o mesmo para
todas as organizações, e replicá-lo por tenant faria cada uma repetir as mesmas chamadas de
API e as mesmas varreduras de site para chegar ao mesmo resultado. O que é do tenant é o
`Lead` — a relação comercial —, e ele nasce na Etapa 12.

`CompanySource` (procedência) não está aqui: ela tem FK para `Provider`, e a ordem de
dependência do CLAUDE.md é `companies` ← `providers`. Ela nasce no app `providers`, na
Etapa 7, junto com quem produz a procedência.
"""

from __future__ import annotations

from django.contrib.gis.db import models
from django.contrib.postgres.indexes import GinIndex
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.text import normalize_name


class Category(BaseModel):
    """Ramo de atuação, em árvore.

    `provider_mapping` guarda a tradução para cada fonte (OSM `amenity=dentist`,
    CNAE `8630-5/04`). É isso que evita categoria hardcoded no código quando entrar o
    quinto provider.
    """

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name=_("categoria pai"),
    )
    slug = models.SlugField(_("identificador"), max_length=120, unique=True)
    name = models.CharField(_("nome"), max_length=120)
    provider_mapping = models.JSONField(_("mapeamento por fonte"), default=dict, blank=True)
    is_active = models.BooleanField(_("ativa"), default=True)

    class Meta:
        verbose_name = _("categoria")
        verbose_name_plural = _("categorias")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Company(BaseModel):
    """Uma empresa. Global, permanente, nunca duplicada por redescoberta."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Ativa")
        INACTIVE = "INACTIVE", _("Inativa")
        CLOSED = "CLOSED", _("Encerrada")
        MERGED = "MERGED", _("Fundida em outra")

    class WebsiteStatus(models.TextChoices):
        NOT_CHECKED = "NOT_CHECKED", _("Ainda não verificado")
        FOUND = "FOUND", _("Site identificado")
        # O rótulo é obrigatório e literal (CLAUDE.md): afirmar que a empresa não tem site
        # é proibido. Ausência na fonte não é ausência no mundo — o OSM tem cobertura
        # irregular no interior, e o produto inteiro perde credibilidade se mentir aqui.
        NOT_FOUND = "NOT_FOUND", _("Site oficial não identificado nas fontes analisadas")

    name = models.CharField(_("nome"), max_length=200)
    normalized_name = models.CharField(_("nome normalizado"), max_length=200, editable=False)
    legal_name = models.CharField(_("razão social"), max_length=200, blank=True)
    trade_name = models.CharField(_("nome fantasia"), max_length=200, blank=True)
    tax_id = models.CharField(_("CNPJ"), max_length=14, null=True, blank=True)
    description = models.TextField(_("descrição"), blank=True)

    status = models.CharField(
        _("situação"), max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    website_status = models.CharField(
        _("situação do site"),
        max_length=16,
        choices=WebsiteStatus.choices,
        default=WebsiteStatus.NOT_CHECKED,
    )

    # Avaliação pública da fonte. Decimal, não float: nota é dado exibido e comparado, e
    # float acumula erro em média e ordenação.
    rating = models.DecimalField(_("nota"), max_digits=2, decimal_places=1, null=True, blank=True)
    review_count = models.PositiveIntegerField(_("avaliações"), default=0)

    # `status=MERGED` sem isto é beco sem saída: quem chegar pela empresa antiga — um link
    # salvo, um `external_id` de fonte, um relatório velho — não tem como achar a que
    # sobreviveu. `SET_NULL` porque apagar a sobrevivente não pode arrastar o histórico.
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_from",
        verbose_name=_("fundida em"),
    )

    discovered_at = models.DateTimeField(_("descoberta em"), auto_now_add=True)
    last_seen_at = models.DateTimeField(_("vista pela última vez em"), null=True, blank=True)
    data_quality = models.JSONField(_("qualidade do dado"), default=dict, blank=True)

    # A anotação é exigida pelo django-stubs: com `through`, o mypy não infere sozinho os
    # dois lados da relação. `CompanyCategory` é referência adiante, resolvida por
    # `from __future__ import annotations`.
    categories: models.ManyToManyField[Category, CompanyCategory] = models.ManyToManyField(
        Category, through="CompanyCategory", related_name="companies", blank=True
    )

    class Meta:
        verbose_name = _("empresa")
        verbose_name_plural = _("empresas")
        ordering = ["name"]
        constraints = [
            # Parcial: CNPJ nulo é comum (MEI sem registro na fonte, empresa só no OSM) e
            # não pode colidir consigo mesmo. `UNIQUE` normal trataria vários NULL como
            # distintos no Postgres, mas a condição deixa a intenção explícita no schema.
            models.UniqueConstraint(
                fields=["tax_id"],
                condition=models.Q(tax_id__isnull=False),
                name="uniq_company_tax_id_quando_preenchido",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_id__isnull=True) | models.Q(tax_id__regex=r"^\d{14}$"),
                name="company_tax_id_14_digitos",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__isnull=True) | models.Q(rating__gte=0, rating__lte=5),
                name="company_rating_entre_0_e_5",
            ),
            # Empresa fundida em si mesma some do sistema: não aparece como ativa nem leva
            # a lugar nenhum. Um merge com os argumentos trocados faria exatamente isso.
            models.CheckConstraint(
                condition=~models.Q(merged_into=models.F("id")),
                name="company_nao_funde_em_si_mesma",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["website_status"]),
            # Similaridade de nome por trigrama, no banco. É o que torna a deduplicação
            # (Etapa 6) viável em milhões de linhas: comparar nome par a par em Python é
            # O(n²) e não termina. A extensão `pg_trgm` já vem de core.0002_extensions.
            #
            # O índice composto de blocking key (cidade + prefixo do nome) fica para a
            # Etapa 6, junto com a query que o usa — a cidade mora em CompanyAddress, e
            # índice sem consulta é custo de escrita sem retorno.
            GinIndex(
                fields=["normalized_name"],
                opclasses=["gin_trgm_ops"],
                name="company_nome_trgm_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_name(self.name)

        # Mesmo cuidado de `geography.City`: quem grava com `update_fields` listando só
        # `name` deixaria o derivado para trás, e a empresa sumiria da busca e do dedup.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "normalized_name"}

        super().save(*args, **kwargs)


class CompanyAddress(BaseModel):
    """Endereço. `city` liga a empresa à base do IBGE (Etapa 4)."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="addresses", verbose_name=_("empresa")
    )
    city = models.ForeignKey(
        "geography.City",
        on_delete=models.PROTECT,
        related_name="company_addresses",
        verbose_name=_("município"),
    )
    street = models.CharField(_("logradouro"), max_length=200, blank=True)
    number = models.CharField(_("número"), max_length=20, blank=True)
    complement = models.CharField(_("complemento"), max_length=100, blank=True)
    district = models.CharField(_("bairro"), max_length=100, blank=True)
    postal_code = models.CharField(_("CEP"), max_length=8, blank=True)
    # O Django cria o índice GiST sozinho para campo geográfico — não escrever à mão.
    location = models.PointField(_("localização"), srid=4326, null=True, blank=True)
    is_primary = models.BooleanField(_("principal"), default=False)
    source_ref = models.CharField(_("referência na fonte"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("endereço")
        verbose_name_plural = _("endereços")
        ordering = ["-is_primary"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(postal_code="") | models.Q(postal_code__regex=r"^\d{8}$"),
                name="address_cep_8_digitos_ou_vazio",
            ),
        ]
        indexes = [models.Index(fields=["city"])]

    def __str__(self) -> str:
        return f"{self.street}, {self.number} — {self.city}"


class CompanyContact(BaseModel):
    """Telefone, WhatsApp ou e-mail.

    `value_raw` guarda o que a fonte mandou e `value_normalized` a forma canônica. Os dois,
    não só o normalizado: quando a normalização recusar um número que deveria valer, é o
    valor cru que permite descobrir por quê.
    """

    class Kind(models.TextChoices):
        PHONE = "PHONE", _("Telefone")
        WHATSAPP = "WHATSAPP", _("WhatsApp")
        EMAIL = "EMAIL", _("E-mail")

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "UNVERIFIED", _("Não verificado")
        VALID = "VALID", _("Válido")
        INVALID = "INVALID", _("Inválido")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="contacts", verbose_name=_("empresa")
    )
    kind = models.CharField(_("tipo"), max_length=16, choices=Kind.choices)
    value_raw = models.CharField(_("valor original"), max_length=200)
    value_normalized = models.CharField(_("valor normalizado"), max_length=200)
    is_primary = models.BooleanField(_("principal"), default=False)
    verification_status = models.CharField(
        _("verificação"),
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    last_verified_at = models.DateTimeField(_("verificado em"), null=True, blank=True)
    confidence = models.DecimalField(_("confiança"), max_digits=3, decimal_places=2, default=1.0)

    class Meta:
        verbose_name = _("contato")
        verbose_name_plural = _("contatos")
        ordering = ["-is_primary", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "kind", "value_normalized"],
                name="uniq_contact_por_empresa_tipo_valor",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="contact_confianca_entre_0_e_1",
            ),
        ]
        indexes = [
            # A supressão da LGPD (Etapa 12) busca por valor normalizado, sem saber a empresa.
            models.Index(fields=["value_normalized"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.value_normalized}"


class CompanyWebsite(BaseModel):
    """Site. `domain` é sinal forte de deduplicação — dois negócios raramente o dividem."""

    class Status(models.TextChoices):
        UNKNOWN = "UNKNOWN", _("Não verificado")
        ONLINE = "ONLINE", _("No ar")
        OFFLINE = "OFFLINE", _("Fora do ar")
        PARKED = "PARKED", _("Domínio estacionado")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="websites", verbose_name=_("empresa")
    )
    url = models.URLField(_("URL"), max_length=500)
    domain = models.CharField(_("domínio"), max_length=253)
    is_primary = models.BooleanField(_("principal"), default=False)
    status = models.CharField(
        _("situação"), max_length=16, choices=Status.choices, default=Status.UNKNOWN
    )
    last_checked_at = models.DateTimeField(_("verificado em"), null=True, blank=True)

    def save(self, *args, **kwargs):
        # Derivado no model, e não em cada chamador: fonte externa manda URL sem esquema
        # (a tag `website` do OSM é assim na maioria das vezes), e uma URL torta no banco
        # faz o guard de SSRF recusá-la depois — classificando dado sujo como ataque.
        from apps.companies.normalization import normalize_url

        if normalizada := normalize_url(self.url):
            self.url = normalizada
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("site")
        verbose_name_plural = _("sites")
        ordering = ["-is_primary"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "domain"], name="uniq_website_por_empresa_dominio"
            ),
        ]
        indexes = [models.Index(fields=["domain"])]

    def __str__(self) -> str:
        return self.domain


class CompanySocialProfile(BaseModel):
    """Perfil em rede social."""

    class Network(models.TextChoices):
        INSTAGRAM = "INSTAGRAM", _("Instagram")
        FACEBOOK = "FACEBOOK", _("Facebook")
        LINKEDIN = "LINKEDIN", _("LinkedIn")
        YOUTUBE = "YOUTUBE", _("YouTube")
        TIKTOK = "TIKTOK", _("TikTok")

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="social_profiles",
        verbose_name=_("empresa"),
    )
    network = models.CharField(_("rede"), max_length=16, choices=Network.choices)
    url = models.URLField(_("URL"), max_length=500)
    handle = models.CharField(_("perfil"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("perfil social")
        verbose_name_plural = _("perfis sociais")
        ordering = ["network"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "network", "url"], name="uniq_perfil_por_empresa_rede_url"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_network_display()}: {self.handle or self.url}"


class CompanyCategory(BaseModel):
    """Classificação da empresa. `assigned_by` diz se veio da fonte, de regra ou de humano."""

    class AssignedBy(models.TextChoices):
        PROVIDER = "PROVIDER", _("Fonte")
        RULE = "RULE", _("Regra")
        MANUAL = "MANUAL", _("Manual")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_categories"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="company_categories"
    )
    is_primary = models.BooleanField(_("principal"), default=False)
    assigned_by = models.CharField(
        _("atribuída por"),
        max_length=16,
        choices=AssignedBy.choices,
        default=AssignedBy.PROVIDER,
    )

    class Meta:
        verbose_name = _("categoria da empresa")
        verbose_name_plural = _("categorias da empresa")
        ordering = ["-is_primary"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "category"], name="uniq_categoria_por_empresa"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} — {self.category.name}"
