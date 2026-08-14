"""Geração de UUIDv7 (RFC 9562).

A stdlib do Python 3.12 não tem `uuid.uuid7`. São dez linhas de aritmética de bytes —
não vale uma dependência. Ver ADR-0006 para o porquê de v7 em vez de v4.

Layout: 48 bits de timestamp em milissegundos, 4 bits de versão, 74 bits aleatórios
(dos quais 2 são a variante). O prefixo temporal é o que dá localidade de inserção no
índice B-tree.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Devolve um UUID versão 7, ordenável pelo instante de criação."""
    timestamp_ms = time.time_ns() // 1_000_000
    data = bytearray(timestamp_ms.to_bytes(6, "big") + os.urandom(10))
    data[6] = (data[6] & 0x0F) | 0x70  # versão 7
    data[8] = (data[8] & 0x3F) | 0x80  # variante RFC 4122
    return uuid.UUID(bytes=bytes(data))


def timestamp_from_uuid7(value: uuid.UUID) -> float:
    """Extrai o instante de criação (epoch em segundos) de um UUIDv7."""
    if value.version != 7:
        raise ValueError(f"UUID versão {value.version} não carrega timestamp")
    return int.from_bytes(value.bytes[:6], "big") / 1000
