"""Logging estruturado em JSON, com correlação por requisição e redação de segredos.

Regra de SECURITY.md: senha, token, secret, cookie e API key nunca aparecem em log.
A redação acontece no filtro, não no ponto de chamada — depender de disciplina em cada
`logger.info()` é como esse tipo de vazamento acontece.
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

REDACTED = "***"

# Casa `password=algo`, `"token": "algo"`, `api_key: algo`, `Authorization: Bearer algo` e
# também `DJANGO_SECRET_KEY=algo`.
#
# O nome da chave aceita prefixo e sufixo (`[\w.-]*`) de propósito: `\bsecret` **não** casa
# dentro de `DJANGO_SECRET_KEY`, porque `_` é caractere de palavra e não existe fronteira
# ali. Sem isso, um despejo de variáveis de ambiente vazaria a chave de sessão — e quem tem
# a SECRET_KEY forja sessão de qualquer usuário.
#
# O grupo do esquema (Bearer/Basic/...) existe para que o token depois dele também seja
# mascarado; sem ele, só a palavra "Bearer" seria redigida e o segredo passaria.
_SECRET_PATTERN = re.compile(
    r"(?i)([\w.\-]*(?:password|passwd|senha|token|secret|api[_-]?key|authorization|cookie)"
    r"[\w.\-]*)"
    r"(\"?\s*[:=]\s*\"?)"
    r"(?:(?:bearer|basic|token|jwt)\s+)?"
    r"([^\s,;\"'}]+)"
)

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "senha",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "csrftoken",
        "sessionid",
    }
)

_RESERVED_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def redact(value: str) -> str:
    return _SECRET_PATTERN.sub(rf"\1\2{REDACTED}", value)


class RequestIDFilter(logging.Filter):
    """Injeta o `request_id` corrente em todo registro de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RedactSecretsFilter(logging.Filter):
    """Mascara segredos na mensagem e nos campos extras do registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = self._redact_args(record.args)
        for key, value in list(record.__dict__.items()):
            # Comparação por conteúdo, não por igualdade: um extra chamado `secret_key` ou
            # `user_token` carrega segredo tanto quanto `secret` ou `token`.
            if any(sensivel in key.lower() for sensivel in _SENSITIVE_KEYS):
                record.__dict__[key] = REDACTED
            elif isinstance(value, str) and key not in _RESERVED_ATTRS:
                record.__dict__[key] = redact(value)
        return True

    @staticmethod
    def _redact_args(args):
        if isinstance(args, dict):
            return {
                k: (
                    REDACTED
                    if any(sensivel in str(k).lower() for sensivel in _SENSITIVE_KEYS)
                    else v
                )
                for k, v in args.items()
            }
        return tuple(redact(a) if isinstance(a, str) else a for a in args)


class JSONFormatter(logging.Formatter):
    """Uma linha JSON por evento — o formato que qualquer coletor de log entende."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "")
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key != "request_id":
                payload[key] = value if _is_json_safe(value) else repr(value)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _is_json_safe(value: object) -> bool:
    return isinstance(value, str | int | float | bool | type(None) | list | dict)
