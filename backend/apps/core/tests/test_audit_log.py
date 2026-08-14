"""AuditLog é append-only. É um controle de segurança, não uma convenção (SECURITY.md)."""

from __future__ import annotations

import pytest

from apps.core.models import AppendOnlyError, AuditLog

pytestmark = pytest.mark.django_db


def _criar() -> AuditLog:
    return AuditLog.objects.create(
        action=AuditLog.Action.CONFIG_CHANGE,
        object_type="Provider",
        changes={"is_enabled": [False, True]},
    )


def test_criacao_funciona():
    log = _criar()
    assert AuditLog.objects.count() == 1
    assert log.id.version == 7


def test_alteracao_e_recusada():
    log = _criar()
    log.action = AuditLog.Action.DELETE
    with pytest.raises(AppendOnlyError):
        log.save()


def test_exclusao_e_recusada():
    log = _criar()
    with pytest.raises(AppendOnlyError):
        log.delete()


def test_exclusao_em_massa_e_recusada():
    """Model.delete() sozinho não protege: queryset.delete() não passa por ele."""
    _criar()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()


def test_update_em_massa_e_recusado():
    _criar()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().update(object_type="Outro")
