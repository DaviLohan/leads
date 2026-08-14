"""Health checks (ver DEPLOYMENT.md).

- `/health/live`  processo vivo. Não toca em dependência. Serve para liveness.
- `/health/ready` Postgres e Redis respondem. Serve para readiness e para tirar a
  instância do balanceador durante um deploy.

Ambos são públicos e não expõem detalhe interno: o corpo diz `ok`/`error` por
dependência, sem host, credencial ou stack trace.
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

_PROBE_KEY = "health:probe"


@require_GET
@never_cache
def live(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
@never_cache
def ready(_request: HttpRequest) -> JsonResponse:
    checks = {"database": _check_database(), "cache": _check_cache()}
    healthy = all(status == "ok" for status in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=200 if healthy else 503,
    )


def _check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("health check do banco falhou")
        return "error"
    return "ok"


def _check_cache() -> str:
    try:
        cache.set(_PROBE_KEY, "1", timeout=10)
        if cache.get(_PROBE_KEY) != "1":
            return "error"
    except Exception:
        logger.exception("health check do cache falhou")
        return "error"
    return "ok"
