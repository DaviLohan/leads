"""Segredo em log é vazamento. O filtro precisa funcionar sem cooperação de quem loga."""

from __future__ import annotations

import json
import logging

import pytest

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


class TestRedacaoDeVariaveisDeAmbiente:
    """`\\bsecret` não casa dentro de `DJANGO_SECRET_KEY` — `_` é caractere de palavra.

    Quem obtém a SECRET_KEY forja sessão de qualquer usuário, então um despejo de ambiente
    em log é vazamento grave. Este é o caso que a fronteira de palavra deixava passar.
    """

    @pytest.mark.parametrize(
        ("linha", "segredo"),
        [
            ("DJANGO_SECRET_KEY=chave-de-sessao", "chave-de-sessao"),
            ("OVERPASS_API_TOKEN=abc123", "abc123"),
            ("DATABASE_PASSWORD=p@ss", "p@ss"),
            ("ANTHROPIC_API_KEY=sk-xyz", "sk-xyz"),
            ("user_password: 12345", "12345"),
        ],
    )
    def test_prefixo_e_sufixo_no_nome_da_chave(self, linha, segredo):
        assert segredo not in redact(linha)

    @pytest.mark.parametrize(
        "prosa", ["senha do usuario esquecida", "cidade=Londrina", "token de acesso expirado"]
    )
    def test_nao_redige_prosa_nem_campo_comum(self, prosa):
        """Redigir demais também custa: log ilegível não é log."""
        assert redact(prosa) == prosa

    def test_extras_com_nome_composto(self):
        registro = logging.LogRecord("x", logging.INFO, "", 0, "msg", None, None)
        registro.secret_key = "k"
        registro.user_token = "t"
        registro.cidade = "Londrina"

        RedactSecretsFilter().filter(registro)

        assert registro.secret_key == REDACTED
        assert registro.user_token == REDACTED
        assert registro.cidade == "Londrina"
