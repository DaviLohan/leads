"""Cliente da API de localidades do IBGE.

Serviço público, gratuito e sem chave. Duas chamadas dão o país inteiro: 27 estados e
~5.570 municípios. Como é um download só, feito de tempos em tempos por um comando de
gestão, não há motivo para uma abstração de provider — `providers` nasce na Etapa 7, para
fontes de *empresas* (ADR-0003), e geografia não passa por aquele pipeline.

Rede tem regra (CLAUDE.md): timeout, retry limitado e backoff exponencial com jitter.
Nunca retry infinito.
"""

from __future__ import annotations

import gzip
import json
import logging
import random
import time
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlsplit

from django.conf import settings

logger = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 1.0
GZIP_MAGIC = b"\x1f\x8b"


class IBGEError(RuntimeError):
    """Falha ao obter dados do IBGE depois de esgotadas as tentativas."""


def _read_body(response) -> bytes:
    """Lê o corpo com teto de tamanho e descomprime se vier gzipado.

    O IBGE responde comprimido mesmo com o `Accept-Encoding: identity` que o urllib manda —
    e o urllib, ao contrário do `requests`, não descomprime sozinho.

    O teto existe porque isto é entrada de rede: sem ele, uma resposta anômala (ou um
    IBGE_API_URL trocado) carregaria o que viesse direto na memória do worker. Ler um byte
    além do limite é o que permite distinguir "no limite" de "estourou".
    """
    limit = settings.IBGE_MAX_BYTES
    body = response.read(limit + 1)
    if len(body) > limit:
        raise IBGEError(f"Resposta do IBGE passou de {limit} bytes.")

    if body[:2] == GZIP_MAGIC:
        body = gzip.decompress(body)
    return body


def _get_json(path: str) -> Any:
    """Baixa e decodifica um recurso da API, com retry e backoff.

    Falha em erro de rede, HTTP e JSON inválido — as três são a mesma coisa para quem
    chama: o dado não veio. O erro sobe; ninguém engole exceção em silêncio (CLAUDE.md).
    """
    url = urljoin(settings.IBGE_API_URL.rstrip("/") + "/", path.lstrip("/"))
    scheme = urlsplit(url).scheme
    if scheme not in ("http", "https"):
        # Esquema vem de settings, mas `file://` num .env mal preenchido leria o disco.
        raise IBGEError(f"Esquema não permitido em IBGE_API_URL: {scheme!r}")

    attempts = settings.IBGE_MAX_ATTEMPTS
    request = urllib.request.Request(  # noqa: S310 - esquema validado logo acima
        url, headers={"User-Agent": settings.IBGE_USER_AGENT, "Accept": "application/json"}
    )

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(  # noqa: S310 - esquema validado logo acima
                request, timeout=settings.IBGE_TIMEOUT_SECONDS
            ) as response:
                return json.loads(_read_body(response))
        # `OSError` cobre de uma vez URLError/HTTPError, TimeoutError e BadGzipFile — para
        # quem chama são a mesma coisa: o dado não veio. `IBGEError` (resposta grande demais)
        # é RuntimeError de propósito: repetir daria o mesmo resultado.
        except (OSError, json.JSONDecodeError) as exc:
            if attempt == attempts:
                raise IBGEError(f"IBGE indisponível após {attempts} tentativas: {url}") from exc
            # Jitter para que várias tentativas não voltem todas no mesmo instante. Não é
            # sorteio com valor de segurança, então `random` basta.
            jitter = 0.5 + random.random()  # noqa: S311
            delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1) * jitter
            logger.warning(
                "IBGE falhou, tentando de novo",
                extra={"url": url, "attempt": attempt, "delay": round(delay, 2), "error": str(exc)},
            )
            time.sleep(delay)

    raise IBGEError(f"IBGE indisponível: {url}")  # pragma: no cover - o laço sempre retorna ou sobe


def fetch_states() -> list[dict[str, Any]]:
    return _get_json("estados")


def fetch_cities() -> list[dict[str, Any]]:
    return _get_json("municipios")
