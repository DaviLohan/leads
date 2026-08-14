from __future__ import annotations

import pytest

from apps.geography.models import City, Region, State
from apps.providers.base import RetentionPolicy
from apps.providers.mock import MockProvider
from apps.providers.models import Provider


@pytest.fixture
def londrina(db):
    parana = State.objects.create(ibge_code="41", uf="PR", name="Paraná", region=Region.SUL)
    return City.objects.create(ibge_code="4113700", name="Londrina", state=parana)


@pytest.fixture
def linha_mock(db):
    return Provider.objects.create(
        slug=MockProvider.slug,
        name="Fonte fictícia",
        retention_policy=RetentionPolicy.PERSIST,
        rate_limit_per_second=1000,
    )


@pytest.fixture
def fonte_mock():
    return MockProvider(rate_limit_per_second=1000)


@pytest.fixture
def dentistas():
    return {"amenity": "dentist"}
