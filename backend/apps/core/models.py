"""Modelos base compartilhados por todos os apps."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.ids import uuid7


class BaseModel(models.Model):
    """Base de todo model do projeto: PK UUIDv7 (ADR-0006) e carimbos de tempo em UTC."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    """QuerySet de dado que pertence a uma organização."""

    def for_organization(self, organization) -> TenantQuerySet:
        if organization is None:
            return self.none()
        return self.filter(organization=organization)


class TenantModel(BaseModel):
    """Base dos models cujo dado é da organização e nunca cruza a fronteira (ADR-0007).

    O filtro é **explícito**, não automático. Um manager que se filtra sozinho a partir do
    request quebra em task Celery — onde não existe request — e esconde a falha justamente
    onde ela custa mais caro. A imposição fica em um ponto só:
    `apps.core.viewsets.TenantViewSet.get_queryset`.

    `PROTECT` na FK: apagar uma organização com dado comercial dentro precisa ser uma
    decisão consciente, não um efeito colateral de cascade.
    """

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["organization"])]


class AppendOnlyError(Exception):
    """Tentativa de alterar ou excluir um registro append-only."""


class AppendOnlyQuerySet(models.QuerySet):
    """QuerySet que recusa alteração em massa — `Model.objects.all().delete()` inclusive."""

    def delete(self):
        raise AppendOnlyError("Registros append-only não podem ser excluídos.")

    def update(self, **kwargs):
        raise AppendOnlyError("Registros append-only não podem ser alterados.")


class AuditLog(BaseModel):
    """Trilha de auditoria append-only (ver SECURITY.md).

    Registra ações relevantes: alteração de usuário e permissões, exclusões, merge de
    empresa, mudança de configuração e de provider. Usuário comum não consegue alterá-la.
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", _("Criação")
        UPDATE = "UPDATE", _("Alteração")
        DELETE = "DELETE", _("Exclusão")
        MERGE = "MERGE", _("Merge")
        LOGIN = "LOGIN", _("Login")
        PERMISSION_CHANGE = "PERMISSION_CHANGE", _("Alteração de permissão")
        CONFIG_CHANGE = "CONFIG_CHANGE", _("Alteração de configuração")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    organization_id = models.UUIDField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=32, choices=Action.choices)
    object_type = models.CharField(max_length=100)
    object_id = models.UUIDField(null=True, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de auditoria")
        verbose_name_plural = _("registros de auditoria")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["organization_id", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type} {self.object_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("AuditLog é append-only: alteração não é permitida.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("AuditLog é append-only: exclusão não é permitida.")
