"""Gravação da trilha de auditoria.

Ponto único para criar `AuditLog`, já preenchendo `request_id` e IP a partir do request.
Espalhar `AuditLog.objects.create(...)` pelo código leva a registros com campos faltando.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.models import AuditLog


def client_ip(request: HttpRequest | None) -> str | None:
    """IP do cliente, considerando o proxy reverso.

    Só o primeiro salto do `X-Forwarded-For` é considerado, e apenas porque em produção há
    um proxy conhecido na frente. Sem proxy confiável, o header é forjável pelo cliente.
    """
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def record_audit(
    *,
    action: str,
    object_type: str,
    object_id: Any = None,
    actor=None,
    organization=None,
    changes: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditLog:
    return AuditLog.objects.create(
        action=action,
        object_type=object_type,
        object_id=getattr(object_id, "pk", object_id),
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        organization_id=getattr(organization, "pk", organization),
        changes=changes or {},
        ip_address=client_ip(request),
        request_id=getattr(request, "request_id", "") if request else "",
    )
