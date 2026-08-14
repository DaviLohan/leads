"""Importação da base geográfica do IBGE.

Recebe o payload já decodificado — não busca na rede. Assim o teste exercita a regra de
verdade com dados fixos, sem depender do IBGE estar de pé, e o comando de gestão decide
se o payload veio da API ou de um arquivo.

Idempotência vem do código IBGE, que é único no banco: reimportar atualiza, não duplica.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.geography.models import City, Region, State

VALID_REGIONS = {choice.value for choice in Region}


@dataclass(frozen=True)
class ImportResult:
    """Quantos registros nasceram e quantos mudaram."""

    created: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated


class GeographyImportError(ValueError):
    """Payload do IBGE em formato inesperado."""


def _uf_id(city: dict[str, Any]) -> int | None:
    """Extrai o id da UF de um município.

    O IBGE devolve a hierarquia por dois caminhos e nem todo município tem os dois:
    os criados depois da revisão de 2017 vêm sem `microrregiao`, só com `regiao-imediata`.
    Tentar apenas um dos caminhos perde municípios em silêncio.
    """
    micro = city.get("microrregiao") or {}
    uf = (micro.get("mesorregiao") or {}).get("UF") or {}
    if not uf:
        imediata = city.get("regiao-imediata") or {}
        uf = (imediata.get("regiao-intermediaria") or {}).get("UF") or {}
    return uf.get("id")


@transaction.atomic
def import_states(payload: list[dict[str, Any]]) -> ImportResult:
    """Grava as unidades federativas. Operação atômica: tudo ou nada (CLAUDE.md)."""
    created = updated = 0
    for item in payload:
        region = ((item.get("regiao") or {}).get("sigla") or "").upper()
        if region not in VALID_REGIONS:
            raise GeographyImportError(f"Região desconhecida em {item.get('sigla')!r}: {region!r}")

        _, was_created = State.objects.update_or_create(
            ibge_code=str(item["id"]),
            defaults={
                "uf": item["sigla"].upper(),
                "name": item["nome"],
                "region": region,
            },
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)

    return ImportResult(created=created, updated=updated)


@transaction.atomic
def import_cities(payload: list[dict[str, Any]]) -> ImportResult:
    """Grava os municípios. Exige que os estados já existam.

    Município órfão é erro, não linha pulada: um payload truncado precisa quebrar a
    importação inteira, não deixar um estado sem cidades e ninguém perceber.
    """
    states_by_ibge_code = {state.ibge_code: state for state in State.objects.all()}
    created = updated = 0

    # ponytail: um `update_or_create` por município — ~11k queries para os 5.570 do país,
    # cerca de meio minuto. É comando de gestão rodado de raro em raro, não caminho de
    # request. Se um dia incomodar, o caminho é `bulk_create(update_conflicts=True)`.
    for item in payload:
        uf_id = _uf_id(item)
        state = states_by_ibge_code.get(str(uf_id))
        if state is None:
            raise GeographyImportError(
                f"Município {item.get('nome')!r} ({item.get('id')}) aponta para a UF {uf_id!r}, "
                "que não está na base. Importe os estados primeiro."
            )

        # `update_or_create` e não `bulk_*`: o `save` do model deriva `normalized_name`.
        _, was_created = City.objects.update_or_create(
            ibge_code=str(item["id"]),
            defaults={"state": state, "name": item["nome"]},
        )
        created, updated = (created + 1, updated) if was_created else (created, updated + 1)

    return ImportResult(created=created, updated=updated)
