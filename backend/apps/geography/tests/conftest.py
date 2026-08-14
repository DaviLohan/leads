"""Payloads do IBGE no formato real da API, reduzidos ao necessário.

Nenhum teste toca a rede (CLAUDE.md). As duas formas de hierarquia estão representadas de
propósito: municípios antigos trazem `microrregiao`, os criados depois da revisão de 2017
só trazem `regiao-imediata`.
"""

from __future__ import annotations

import pytest

SUL = {"id": 4, "sigla": "S", "nome": "Sul"}
SUDESTE = {"id": 3, "sigla": "SE", "nome": "Sudeste"}

UF_PR = {"id": 41, "sigla": "PR", "nome": "Paraná", "regiao": SUL}
UF_SP = {"id": 35, "sigla": "SP", "nome": "São Paulo", "regiao": SUDESTE}


@pytest.fixture
def estados():
    return [
        {"id": 41, "sigla": "PR", "nome": "Paraná", "regiao": SUL},
        {"id": 35, "sigla": "SP", "nome": "São Paulo", "regiao": SUDESTE},
    ]


@pytest.fixture
def municipios():
    return [
        # Caminho clássico: microrregiao → mesorregiao → UF.
        {
            "id": 4113700,
            "nome": "Londrina",
            "microrregiao": {
                "id": 41011,
                "nome": "Londrina",
                "mesorregiao": {"id": 4103, "nome": "Norte Central Paranaense", "UF": UF_PR},
            },
        },
        {
            "id": 4106902,
            "nome": "Curitiba",
            "microrregiao": {
                "id": 41037,
                "nome": "Curitiba",
                "mesorregiao": {"id": 4110, "nome": "Metropolitana de Curitiba", "UF": UF_PR},
            },
        },
        # Caminho novo: sem microrregiao, só regiao-imediata → regiao-intermediaria → UF.
        {
            "id": 3550308,
            "nome": "São Paulo",
            "microrregiao": None,
            "regiao-imediata": {
                "id": 350001,
                "nome": "São Paulo",
                "regiao-intermediaria": {"id": 3501, "nome": "São Paulo", "UF": UF_SP},
            },
        },
    ]


@pytest.fixture
def base_importada(db, estados, municipios):
    """Base geográfica pronta para os testes de API."""
    from apps.geography.services import import_cities, import_states

    import_states(estados)
    import_cities(municipios)
