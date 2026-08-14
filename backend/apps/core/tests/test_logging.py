"""Segredo em log é vazamento. O filtro precisa funcionar sem cooperação de quem loga."""

from __future__ import annotations

import json
import logging

from apps.core.logging import (
    REDACTED,
    JSONFormatter,
    RedactSecretsFilter,
    RequestIDFilter,
    redact,
    request_id_var,
)


def _record(msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord("teste", logging.INFO, __file__, 1, msg, None, None)
    record.__dict__.update(extra)
    return record


def test_redige_segredos_na_mensagem():
    assert redact("password=abc123") == f"password={REDACTED}"
    assert redact('{"token": "xyz"}') == f'{{"token": "{REDACTED}"}}'
    assert redact("Authorization: Bearer eyJhbGci") == f"Authorization: {REDACTED}"
    assert redact("api_key=segredo, outro=ok") == f"api_key={REDACTED}, outro=ok"


def test_nao_estraga_mensagem_comum():
    assert redact("empresa encontrada em Londrina/PR") == "empresa encontrada em Londrina/PR"


def test_filtro_redige_campo_extra_sensivel():
    record = _record("login", password="senhaSuperSecreta", user="ana@exemplo.com")
    RedactSecretsFilter().filter(record)
    assert record.password == REDACTED
    assert record.user == "ana@exemplo.com"


def test_filtro_redige_mensagem_do_record():
    record = _record("conectando com api_key=abc")
    RedactSecretsFilter().filter(record)
    assert "abc" not in record.msg


def test_formatter_gera_json_com_request_id():
    token = request_id_var.set("req-123")
    try:
        record = _record("empresa criada", company_id="uuid-1")
        RequestIDFilter().filter(record)
        payload = json.loads(JSONFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert payload["message"] == "empresa criada"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-123"
    assert payload["company_id"] == "uuid-1"
    assert "timestamp" in payload


def test_formatter_serializa_valor_nao_json():
    record = _record("evento", obj=object())
    payload = json.loads(JSONFormatter().format(record))
    assert isinstance(payload["obj"], str)
