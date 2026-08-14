"""Aplicação Celery.

Tarefas demoradas (coleta, análise de site, enriquecimento, scoring, relatórios) nunca
bloqueiam requisição web. Ver CLAUDE.md: task é casca fina, recebe IDs e é idempotente.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("leads")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:
    """Prova que o worker está processando. Usada só na verificação da fundação."""
    return f"ok:{self.request.id}"
