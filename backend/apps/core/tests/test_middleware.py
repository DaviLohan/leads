"""Correlação de requisição e headers de segurança."""

from __future__ import annotations

from apps.core.middleware import REQUEST_ID_HEADER


def test_gera_request_id_quando_ausente(client):
    response = client.get("/health/live")
    assert response[REQUEST_ID_HEADER]


def test_reaproveita_request_id_do_cliente(client):
    response = client.get("/health/live", headers={"x-request-id": "abc-123"})
    assert response[REQUEST_ID_HEADER] == "abc-123"


def test_sanitiza_request_id_malicioso(client):
    """O valor entra em log: não pode carregar quebra de linha nem ser gigante."""
    response = client.get("/health/live", headers={"x-request-id": "a\nb<script> " + "x" * 200})
    devolvido = response[REQUEST_ID_HEADER]
    assert "\n" not in devolvido
    assert "<" not in devolvido
    assert len(devolvido) <= 64


def test_csp_presente_na_resposta(client):
    response = client.get("/health/live")
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]


def test_headers_de_seguranca_do_django(client):
    response = client.get("/health/live")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["X-Frame-Options"] == "DENY"
