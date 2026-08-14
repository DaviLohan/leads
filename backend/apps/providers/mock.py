"""Fonte determinística para testes e desenvolvimento (ADR-0003, regra 5).

Nenhum teste do projeto sai para a rede, e nenhum depende de API paga. Sem isto, a suíte de
dedup, score e CRM ficaria refém do Overpass público estar de pé — e a CI viraria loteria.

Os dados imitam o formato real do OSM, incluindo as imperfeições que importam: dado
faltando, telefone com máscara, dois telefones na mesma tag, `contact:` misturado com a
grafia antiga. Um mock limpo demais esconde exatamente os bugs que ele deveria pegar.
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.providers.base import BaseProvider, RawResult, RetentionPolicy, SearchQuery

# Cinco estabelecimentos em Londrina (4113700). A grafia de cada um é diferente de propósito.
ELEMENTOS: list[dict] = [
    {
        "type": "node",
        "id": 1001,
        "lat": -23.3164,
        "lon": -51.1622,
        "tags": {
            "amenity": "dentist",
            "name": "Clínica Odontológica São José",
            "phone": "(43) 3324-1000",
            "website": "https://www.saojose-odonto.com.br/contato",
            "addr:street": "Avenida Higienópolis",
            "addr:housenumber": "1200",
            "addr:suburb": "Centro",
            "addr:postcode": "86015-010",
        },
    },
    {
        # Grafia `contact:`, dois telefones na mesma tag e sem endereço — tudo comum no OSM.
        "type": "way",
        "id": 2002,
        "center": {"lat": -23.3201, "lon": -51.1701},
        "tags": {
            "amenity": "dentist",
            "name": "Odontologia Integrada Paraná",
            "contact:phone": "(43) 3325-2000; (43) 99999-8888",
            "contact:website": "http://odontoparana.com.br",
            "contact:email": "Contato@OdontoParana.com.BR",
        },
    },
    {
        # Sem site: o caso majoritário. Verificado no Overpass real — dos 10 dentistas
        # mapeados em Londrina, 1 tinha website.
        "type": "node",
        "id": 3003,
        "lat": -23.3100,
        "lon": -51.1550,
        "tags": {
            "amenity": "dentist",
            "name": "Dr. Sérgio Yokoyama",
            "addr:street": "Rua Paranaguá",
            "addr:housenumber": "45",
        },
    },
    {
        # Telefone inválido: 8 dígitos começando com 9 é celular sem o nono dígito. A
        # normalização recusa, e a empresa entra sem telefone em vez de com um errado.
        "type": "node",
        "id": 4004,
        "lat": -23.3050,
        "lon": -51.1600,
        "tags": {"amenity": "dentist", "name": "Consultório Tanaka", "phone": "43 9999-8888"},
    },
    {
        # Sem `name`: geometria solta, não estabelecimento. Tem de ser descartado.
        "type": "node",
        "id": 5005,
        "lat": -23.3000,
        "lon": -51.1500,
        "tags": {"amenity": "dentist", "opening_hours": "Mo-Fr 09:00-18:00"},
    },
]


class MockProvider(BaseProvider):
    slug = "mock"
    retention_policy = RetentionPolicy.PERSIST
    rate_limit_per_second = 1000.0  # sem rede, sem motivo para segurar

    def search_businesses(self, query: SearchQuery) -> Iterable[RawResult]:
        for elemento in ELEMENTOS[: query.limit]:
            tags = elemento.get("tags") or {}
            if not tags.get("name"):
                continue
            # Respeita o filtro de tags como a fonte real faria.
            if any(tags.get(chave) != valor for chave, valor in query.tags.items()):
                continue
            yield RawResult(external_id=f"{elemento['type']}/{elemento['id']}", payload=elemento)

    def normalize_result(self, raw: RawResult):
        """O formato é o do OSM, então a conversão é a mesma — não vale duplicá-la."""
        from apps.providers.overpass import normalize_osm_element

        return normalize_osm_element(raw)
