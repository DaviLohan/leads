"""OpenStreetMap via Overpass — a fonte real do MVP (ADR-0004).

Grátis, sem chave, e os dados podem virar registro permanente sob a ODbL, com atribuição.
É o que torna o princípio de "empresa é entidade permanente" legítimo — o Google Places
proíbe justamente isso.

## O recorte por município

Municípios brasileiros no OSM carregam a tag `IBGE:GEOCODIGO` na relação de fronteira, com
o mesmo código de sete dígitos que a Etapa 4 importou. Isso liga as duas bases sem depender
de nome, que é ambíguo ("Santa Luzia" existe em oito estados).

O idioma tem de ser `map_to_area`, não `area[tag=...]`. Verificado contra o endpoint
público: filtrar o índice de áreas por tag arbitrária dá **504** (o índice não é feito para
isso), enquanto achar a relação e convertê-la em área responde em segundos.

## Uso responsável

O endpoint público é comunitário e pode sair do ar a qualquer momento. ≤1 req/s, backoff
com jitter, User-Agent identificando a aplicação e endpoint configurável (ADR-0004). Varrer
o Brasil inteiro contra ele é abuso — escala exige instância própria ou extratos Geofabrik.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.request
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from django.conf import settings

from apps.providers.base import (
    BaseProvider,
    ProviderError,
    RawResult,
    RetentionPolicy,
    SearchQuery,
)

if TYPE_CHECKING:  # ciclo em tempo de import; só o verificador de tipos lê
    from apps.companies.dedup import CompanyCandidate

logger = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 2.0

# Tags de contato no OSM vêm em duas grafias: a antiga (`phone`) e a do esquema `contact:`.
# As duas convivem no mundo real, então as duas são lidas.
TAGS_TELEFONE = ("phone", "contact:phone", "contact:mobile", "mobile")
TAGS_SITE = ("website", "contact:website", "url")
TAGS_EMAIL = ("email", "contact:email")


class OverpassProvider(BaseProvider):
    slug = "osm-overpass"
    retention_policy = RetentionPolicy.PERSIST
    # Piso conservador da política de uso justo do OSM (ADR-0004). O valor efetivo vem da
    # linha do banco, semeada a partir de OVERPASS_RATE_LIMIT_PER_SECOND.
    rate_limit_per_second = 1.0

    # --- consulta -------------------------------------------------------------

    def build_query(self, query: SearchQuery) -> str:
        filtros = "".join(f'["{k}"="{v}"]' for k, v in sorted(query.tags.items()))
        return (
            f"[out:json][timeout:{settings.OVERPASS_TIMEOUT_SECONDS}];\n"
            f'rel["IBGE:GEOCODIGO"="{query.ibge_code}"]["boundary"="administrative"];\n'
            f"map_to_area->.a;\n"
            f"nwr{filtros}(area.a);\n"
            f"out center tags {query.limit};"
        )

    def search_businesses(self, query: SearchQuery) -> Iterable[RawResult]:
        if not query.ibge_code.isdigit() or not query.tags:
            raise ProviderError("Busca no Overpass exige código IBGE numérico e ao menos uma tag.")

        payload = self._post(self.build_query(query))

        for elemento in payload.get("elements", []):
            tags = elemento.get("tags") or {}
            # Elemento sem nome não é estabelecimento identificável — é geometria solta.
            if not tags.get("name"):
                continue
            yield RawResult(
                external_id=f"{elemento['type']}/{elemento['id']}",
                payload=elemento,
            )

    def _post(self, corpo: str) -> dict[str, Any]:
        """Envia a consulta, com retry limitado e backoff (CLAUDE.md)."""
        url = settings.OVERPASS_API_URL
        if urlsplit(url).scheme not in ("http", "https"):
            raise ProviderError(f"OVERPASS_API_URL com esquema não permitido: {url!r}")

        tentativas = settings.OVERPASS_MAX_ATTEMPTS
        for tentativa in range(1, tentativas + 1):
            self.check_rate_limit()
            try:
                requisicao = urllib.request.Request(  # noqa: S310 - esquema validado acima
                    url,
                    data=corpo.encode("utf-8"),
                    headers={
                        "User-Agent": settings.OVERPASS_USER_AGENT,
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                )
                with urllib.request.urlopen(  # noqa: S310 - esquema validado acima
                    requisicao, timeout=settings.OVERPASS_TIMEOUT_SECONDS
                ) as resposta:
                    bruto = resposta.read(settings.OVERPASS_MAX_BYTES + 1)
                if len(bruto) > settings.OVERPASS_MAX_BYTES:
                    # Não é transitório: repetir traria a mesma resposta grande demais.
                    raise ProviderError(
                        f"Resposta do Overpass passou de {settings.OVERPASS_MAX_BYTES} bytes. "
                        "Recorte a busca."
                    )
                return json.loads(bruto)
            except (OSError, json.JSONDecodeError) as exc:
                if tentativa == tentativas:
                    raise ProviderError(
                        f"Overpass indisponível após {tentativas} tentativas."
                    ) from exc
                jitter = 0.5 + random.random()  # noqa: S311 - espalha tentativas, não é segredo
                espera = BACKOFF_BASE_SECONDS * 2 ** (tentativa - 1) * jitter
                logger.warning(
                    "Overpass falhou, tentando de novo",
                    extra={"attempt": tentativa, "delay": round(espera, 2), "error": str(exc)},
                )
                time.sleep(espera)

        raise ProviderError("Overpass indisponível.")  # pragma: no cover - o laço sempre sai antes

    # --- normalização ---------------------------------------------------------

    def normalize_result(self, raw: RawResult) -> CompanyCandidate:
        return normalize_osm_element(raw)


def normalize_osm_element(raw: RawResult) -> CompanyCandidate:
    """Converte um elemento do OSM no DTO comum.

    Função de módulo, não método: o `MockProvider` fala o mesmo formato e chama daqui. Como
    método, ele precisaria invocar `OverpassProvider.normalize_result(self, ...)` com `self`
    de outra classe — truque que funciona e mente sobre o tipo.

    Os imports são locais de propósito: `companies.dedup` não pode ser importado no topo sem
    criar ciclo, e a conversão é o único ponto deste pacote que precisa dele.
    """
    from apps.companies.dedup import CompanyCandidate
    from apps.companies.normalization import normalize_domain, normalize_phone

    tags = raw.payload.get("tags") or {}
    centro = raw.payload.get("center") or raw.payload

    telefones = tuple(
        dict.fromkeys(  # remove repetição preservando a ordem
            numero
            for chave in TAGS_TELEFONE
            for bruto in _separar(tags.get(chave))
            if (numero := normalize_phone(bruto))
        )
    )
    url = next((tags[c] for c in TAGS_SITE if tags.get(c)), "")
    emails = tuple(
        dict.fromkeys(
            e.strip().lower() for chave in TAGS_EMAIL for e in _separar(tags.get(chave)) if "@" in e
        )
    )

    return CompanyCandidate(
        name=tags["name"].strip(),
        domain=normalize_domain(url),
        website_url=url,
        phones=telefones,
        emails=emails,
        description=tags.get("description", "").strip(),
        street=tags.get("addr:street", "").strip(),
        number=tags.get("addr:housenumber", "").strip(),
        district=(tags.get("addr:suburb") or tags.get("addr:neighbourhood") or "").strip(),
        postal_code="".join(filter(str.isdigit, tags.get("addr:postcode", "")))[:8],
        latitude=centro.get("lat"),
        longitude=centro.get("lon"),
    )


def _separar(valor: str | None) -> list[str]:
    """O OSM separa valores múltiplos por `;` — dois telefones numa tag só é comum."""
    return [p.strip() for p in (valor or "").split(";") if p.strip()]
