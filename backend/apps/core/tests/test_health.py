"""Health checks alimentam o balanceador. Se mentirem, o deploy derruba o serviço."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse


def test_live_nao_exige_autenticacao(client):
    response = client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_com_dependencias_ok(client):
    response = client.get(reverse("health-ready"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "cache": "ok"}


@pytest.mark.django_db
def test_ready_responde_503_quando_banco_falha(client):
    with patch("apps.core.health._check_database", return_value="error"):
        response = client.get(reverse("health-ready"))
    assert response.status_code == 503
    assert response.json()["status"] == "error"


@pytest.mark.django_db
def test_ready_responde_503_quando_cache_falha(client):
    with patch("apps.core.health._check_cache", return_value="error"):
        response = client.get(reverse("health-ready"))
    assert response.status_code == 503


def test_endpoint_de_api_responde_sem_autenticacao(client):
    """Prova o caminho que o rewrite do Next.js usa (ADR-0005)."""
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
