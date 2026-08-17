"""CRM: a relação comercial entre uma organização e uma empresa.

Aqui está a fronteira do ADR-0007 na prática. `Company` é global — o que ela é no mundo vale
para todo mundo. `Lead` é do tenant: que uma organização esteja negociando com ela, em que
estágio, com que histórico, é só dela. Duas organizações prospectando a mesma empresa têm
dois leads e nenhum acesso ao histórico da outra.

`Interaction` é append-only: mudança de estágio vira registro, nunca sobrescreve. Um
histórico comercial que se pode reescrever não serve para decidir nada — e é o único
registro de que a abordagem aconteceu.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import AppendOnlyError, AppendOnlyQuerySet, BaseModel, TenantModel


class Pipeline(TenantModel):
    """O funil da organização. Uma organização pode ter mais de um."""

    name = models.CharField(_("nome"), max_length=100)
    is_default = models.BooleanField(_("padrão"), default=False)

    class Meta:
        verbose_name = _("funil")
        verbose_name_plural = _("funis")
        ordering = ["name"]
        constraints = [
            # Um padrão por organização: dois "padrões" fariam a criação de lead escolher
            # arbitrariamente, e o lead apareceria no funil errado.
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(is_default=True),
                name="uniq_funil_padrao_por_organizacao",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def first_stage(self) -> PipelineStage | None:
        return self.stages.order_by("position").first()


class PipelineStage(BaseModel):
    """Uma coluna do funil. O escopo vem do `Pipeline`."""

    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.CASCADE, related_name="stages", verbose_name=_("funil")
    )
    code = models.SlugField(_("código"), max_length=40)
    name = models.CharField(_("nome"), max_length=60)
    position = models.PositiveSmallIntegerField(_("posição"))
    # Estágio final: ganho, perdido ou não-contatar. Lead aqui sai da fila de trabalho.
    is_terminal = models.BooleanField(_("encerra o lead"), default=False)
    is_won = models.BooleanField(_("representa ganho"), default=False)

    class Meta:
        verbose_name = _("estágio")
        verbose_name_plural = _("estágios")
        ordering = ["pipeline", "position"]
        constraints = [
            models.UniqueConstraint(fields=["pipeline", "code"], name="uniq_estagio_por_funil"),
            models.UniqueConstraint(fields=["pipeline", "position"], name="uniq_posicao_por_funil"),
        ]

    def __str__(self) -> str:
        return self.name


class Lead(TenantModel):
    """Uma empresa sendo prospectada por uma organização."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="leads",
        verbose_name=_("empresa"),
    )
    stage = models.ForeignKey(
        PipelineStage, on_delete=models.PROTECT, related_name="leads", verbose_name=_("estágio")
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leads",
        verbose_name=_("responsável"),
    )
    # Cópia do score no momento em que o lead nasceu. O score da empresa muda quando o site
    # muda; a prioridade com que este lead entrou na fila, não. Guardar os dois permite ver
    # que a empresa "melhorou" — e que a oportunidade encolheu.
    score_snapshot = models.PositiveSmallIntegerField(_("score na entrada"), default=0)
    last_contacted_at = models.DateTimeField(_("último contato"), null=True, blank=True)
    next_action_at = models.DateTimeField(_("próxima ação"), null=True, blank=True)

    # Sem manager próprio: `TenantModel` já traz `for_organization`, que é o que o
    # `TenantViewSet` exige. Um queryset só para acrescentar um filtro duplicaria aquele
    # método e ainda colidiria com o tipo declarado na base.

    class Meta:
        verbose_name = _("lead")
        verbose_name_plural = _("leads")
        ordering = ["-created_at"]
        constraints = [
            # Uma empresa é um lead por organização. Sem isso, dois vendedores da mesma casa
            # ligariam para o mesmo cliente sem saber um do outro.
            models.UniqueConstraint(
                fields=["organization", "company"], name="uniq_lead_por_organizacao_empresa"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "stage"]),
            models.Index(fields=["organization", "-score_snapshot"]),
            models.Index(fields=["organization", "next_action_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} ({self.stage.name})"


class InteractionQuerySet(AppendOnlyQuerySet):
    def for_organization(self, organization) -> InteractionQuerySet:
        if organization is None:
            return self.none()
        return self.filter(lead__organization=organization)


class Interaction(BaseModel):
    """Um evento no histórico do lead. **Append-only.**

    Histórico comercial que se pode reescrever não serve para decidir nada, e é o único
    registro de que a abordagem aconteceu — inclusive para provar consentimento e contato
    diante da LGPD.

    Mudança de estágio entra aqui como `STATUS_CHANGE`, gerada pelo serviço, não pelo
    usuário: assim a linha do tempo conta a história inteira sem depender de disciplina.
    """

    class Kind(models.TextChoices):
        CALL = "CALL", _("Ligação")
        WHATSAPP = "WHATSAPP", _("WhatsApp")
        EMAIL = "EMAIL", _("E-mail")
        MEETING = "MEETING", _("Reunião")
        PROPOSAL = "PROPOSAL", _("Proposta")
        NOTE = "NOTE", _("Observação")
        STATUS_CHANGE = "STATUS_CHANGE", _("Mudança de estágio")

    class Outcome(models.TextChoices):
        NO_ANSWER = "NO_ANSWER", _("Sem resposta")
        ANSWERED = "ANSWERED", _("Atendeu")
        INTERESTED = "INTERESTED", _("Interessado")
        NOT_INTERESTED = "NOT_INTERESTED", _("Sem interesse")
        SCHEDULED = "SCHEDULED", _("Agendou")

    # Tipos que representam contato com a empresa — e só eles atualizam `last_contacted_at`.
    # Anotação interna e mudança de estágio não são contato, e contá-los faria o time achar
    # que falou com o cliente quando só mexeu no sistema.
    KINDS_DE_CONTATO = (Kind.CALL, Kind.WHATSAPP, Kind.EMAIL, Kind.MEETING, Kind.PROPOSAL)

    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="interactions", verbose_name=_("lead")
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="interactions",
        verbose_name=_("autor"),
    )
    kind = models.CharField(_("tipo"), max_length=20, choices=Kind.choices)
    description = models.TextField(_("descrição"), blank=True)
    outcome = models.CharField(_("resultado"), max_length=20, choices=Outcome.choices, blank=True)
    next_action = models.CharField(_("próxima ação"), max_length=200, blank=True)
    next_action_at = models.DateTimeField(_("quando"), null=True, blank=True)
    occurred_at = models.DateTimeField(_("ocorreu em"), default=timezone.now)

    objects = InteractionQuerySet.as_manager()

    class Meta:
        verbose_name = _("interação")
        verbose_name_plural = _("interações")
        # Desempate por `-id` (uuid7 é ordenado no tempo): dois eventos no mesmo instante —
        # a mudança de estágio que o serviço grava e a interação que o usuário registrou —
        # sairiam em ordem arbitrária, e o histórico apareceria de cabeça para baixo.
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["lead", "-occurred_at"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.lead.company.name}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Interação é append-only: alteração não é permitida.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Interação é append-only: exclusão não é permitida.")


class Note(BaseModel):
    """Anotação interna sobre o lead. Editável, ao contrário da interação.

    Diferença que justifica a tabela separada: interação é *evento* ("liguei terça"), e por
    isso é append-only; anotação é *conhecimento* ("o dono é irmão do concorrente"), que se
    corrige quando estava errado.
    """

    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="notes", verbose_name=_("lead")
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notes",
        verbose_name=_("autor"),
    )
    body = models.TextField(_("texto"))

    class Meta:
        verbose_name = _("anotação")
        verbose_name_plural = _("anotações")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.body[:60]


class Task(BaseModel):
    """Compromisso agendado sobre um lead."""

    class Status(models.TextChoices):
        OPEN = "OPEN", _("Aberta")
        DONE = "DONE", _("Concluída")
        CANCELLED = "CANCELLED", _("Cancelada")

    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="tasks", verbose_name=_("lead")
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
        verbose_name=_("responsável"),
    )
    title = models.CharField(_("título"), max_length=200)
    due_at = models.DateTimeField(_("prazo"))
    status = models.CharField(
        _("situação"), max_length=16, choices=Status.choices, default=Status.OPEN
    )

    class Meta:
        verbose_name = _("tarefa")
        verbose_name_plural = _("tarefas")
        ordering = ["due_at"]
        indexes = [models.Index(fields=["status", "due_at"])]

    def __str__(self) -> str:
        return self.title


class SuppressionEntry(TenantModel):
    """Quem esta organização não pode contatar (PROJECT_PLAN §3.4).

    Por **identificador normalizado**, e não por empresa: MEI e profissional liberal são
    pessoa física, e a mesma pessoa reaparece com outro `company_id` por outra busca ou
    outro provider. Suprimir por empresa deixaria o telefone escapar na próxima varredura.

    Base legal: legítimo interesse com opt-out registrado. Por isso `reason` e `created_by`
    não são enfeite — são a prova de que o pedido existiu e de quem o registrou.
    """

    class Kind(models.TextChoices):
        PHONE = "PHONE", _("Telefone")
        EMAIL = "EMAIL", _("E-mail")
        DOMAIN = "DOMAIN", _("Domínio")
        TAX_ID = "TAX_ID", _("CNPJ")
        COMPANY = "COMPANY", _("Empresa")

    identifier_kind = models.CharField(_("tipo"), max_length=16, choices=Kind.choices)
    # Já normalizado por `companies.normalization` — telefone em E.164, domínio sem `www`.
    # Guardar cru faria "(43) 3324-1000" e "+554333241000" serem duas entradas diferentes, e
    # o opt-out vazaria na primeira delas.
    identifier_value = models.CharField(_("valor"), max_length=200)
    reason = models.CharField(_("motivo"), max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suppressions",
        verbose_name=_("registrado por"),
    )

    class Meta:
        verbose_name = _("supressão")
        verbose_name_plural = _("supressões")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "identifier_kind", "identifier_value"],
                name="uniq_supressao_por_org_tipo_valor",
            ),
        ]
        indexes = [
            # Índice usado pela verificação antes de criar lead e antes de contatar: é
            # consulta de caminho quente, feita por identificador.
            models.Index(fields=["organization", "identifier_kind", "identifier_value"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_identifier_kind_display()}: {self.identifier_value}"


class CompanyList(TenantModel):
    """Uma lista de trabalho: "Dentistas de Curitiba", "Ligar amanhã".

    É do tenant, como o `Lead` — a empresa é pública, mas o recorte que uma organização faz
    dela é dela. Lista **não** é estágio de funil e não é lead: serve para separar um lote
    antes de decidir o que fazer com ele, e a mesma empresa pode estar em várias.
    """

    name = models.CharField(_("nome"), max_length=120)
    description = models.CharField(_("descrição"), max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="company_lists",
        verbose_name=_("criada por"),
    )

    class Meta:
        verbose_name = _("lista")
        verbose_name_plural = _("listas")
        ordering = ["name"]
        constraints = [
            # Dois "Dentistas Curitiba" na mesma organização é erro de digitação, não intenção:
            # o time salvaria metade do lote em cada uma e trabalharia com a lista errada.
            models.UniqueConstraint(
                fields=["organization", "name"], name="uniq_lista_por_organizacao_nome"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CompanyListItem(BaseModel):
    """Uma empresa dentro de uma lista. O escopo vem da lista."""

    company_list = models.ForeignKey(
        CompanyList, on_delete=models.CASCADE, related_name="items", verbose_name=_("lista")
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="list_items",
        verbose_name=_("empresa"),
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="list_items",
        verbose_name=_("adicionada por"),
    )

    class Meta:
        verbose_name = _("item da lista")
        verbose_name_plural = _("itens da lista")
        ordering = ["-created_at"]
        constraints = [
            # A idempotência de "salvar em lista" vem daqui, e não de um `if exists` em
            # Python: selecionar as mesmas 20 empresas duas vezes não duplica nada.
            models.UniqueConstraint(
                fields=["company_list", "company"], name="uniq_empresa_por_lista"
            ),
        ]
        indexes = [models.Index(fields=["company_list", "company"])]

    def __str__(self) -> str:
        return f"{self.company_list.name}: {self.company.name}"
