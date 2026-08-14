"""UUIDv7 é a PK de tudo (ADR-0006). Se o layout estiver errado, o banco inteiro herda o erro."""

from __future__ import annotations

import time
import uuid

from apps.core.ids import timestamp_from_uuid7, uuid7


def test_versao_e_variante_corretas():
    value = uuid7()
    assert value.version == 7
    assert (value.bytes[8] & 0xC0) == 0x80  # variante RFC 4122


def test_ordenavel_no_tempo():
    """A razão de existir do v7: ordem de geração = ordem de valor."""
    primeiro = uuid7()
    time.sleep(0.005)
    segundo = uuid7()
    assert primeiro < segundo
    assert primeiro.bytes < segundo.bytes


def test_valores_distintos():
    gerados = {uuid7() for _ in range(1000)}
    assert len(gerados) == 1000


def test_timestamp_recuperavel():
    antes = time.time()
    value = uuid7()
    depois = time.time()
    extraido = timestamp_from_uuid7(value)
    assert antes - 0.001 <= extraido <= depois + 0.001


def test_timestamp_rejeita_uuid_de_outra_versao():
    try:
        timestamp_from_uuid7(uuid.uuid4())
    except ValueError as exc:
        assert "versão" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("deveria ter recusado um UUIDv4")
