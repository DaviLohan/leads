"""Leitura de variáveis de ambiente.

A stdlib resolve — não há dependência extra aqui. O carregamento do arquivo `.env` é
responsabilidade do Docker Compose (`env_file`), não da aplicação.
"""

from __future__ import annotations

import os


class ConfigurationError(Exception):
    """Variável de ambiente obrigatória ausente ou inválida."""


_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise ConfigurationError(f"Variável de ambiente obrigatória ausente: {name}")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    raise ConfigurationError(f"{name} deve ser booleano, recebido: {raw!r}")


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} deve ser inteiro, recebido: {raw!r}") from exc
