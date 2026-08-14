from __future__ import annotations

import pytest

from apps.companies.models import Category
from apps.geography.models import City, Region, State
from apps.providers.mock import MockProvider
from apps.providers.models import Provider


@pytest.fixture
def parana(db):
    return State.objects.create(ibge_code="41", uf="PR", name="Paraná", region=Region.SUL)


@pytest.fixture
def londrina(parana):
    return City.objects.create(ibge_code="4113700", name="Londrina", state=parana)


@pytest.fixture
def maringa(parana):
    return City.objects.create(ibge_code="4115200", name="Maringá", state=parana)


@pytest.fixture
def sao_paulo(db):
    sp = State.objects.create(ibge_code="35", uf="SP", name="São Paulo", region=Region.SUDESTE)
    return City.objects.create(ibge_code="3550308", name="São Paulo", state=sp)


@pytest.fixture
def dentistas(db):
    return Category.objects.create(
        slug="dentistas",
        name="Dentistas",
        provider_mapping={MockProvider.slug: {"amenity": "dentist"}},
    )


@pytest.fixture
def sem_mapeamento(db):
    """Categoria que nenhuma fonte sabe traduzir — não pode virar trabalho."""
    return Category.objects.create(slug="consultorias", name="Consultorias")


@pytest.fixture
def fonte(db):
    return Provider.objects.create(
        slug=MockProvider.slug, name="Fonte fictícia", rate_limit_per_second=1000
    )


@pytest.fixture
def criar_busca(db, org, londrina, dentistas, fonte):
    from apps.discovery.models import Search

    def _criar(**criterios):
        padrao = {
            "city_ids": [str(londrina.id)],
            "category_ids": [str(dentistas.id)],
            "provider_slugs": [fonte.slug],
        }
        return Search.objects.create(
            organization=org, name="Busca de teste", criteria={**padrao, **criterios}
        )

    return _criar
