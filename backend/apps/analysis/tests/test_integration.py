"""O gancho: empresa descoberta entra na fila de análise sozinha (PROJECT_PLAN §4)."""

import pytest
from django.test import override_settings

from apps.analysis.models import WebsiteScan
from apps.companies.models import Company
from apps.providers.ingestion import ingest_city
from apps.providers.mock import MockProvider
from apps.providers.models import Provider

pytestmark = pytest.mark.django_db


@pytest.fixture
def londrina(db):
    from apps.geography.models import City, Region, State

    pr = State.objects.create(ibge_code="41", uf="PR", name="Paraná", region=Region.SUL)
    return City.objects.create(ibge_code="4113700", name="Londrina", state=pr)


@pytest.fixture
def fonte(db):
    return Provider.objects.create(
        slug=MockProvider.slug, name="Fictícia", rate_limit_per_second=1000
    )


def _varrer(londrina, fonte):
    return ingest_city(
        provider=MockProvider(rate_limit_per_second=1000),
        provider_row=fonte,
        city=londrina,
        tags={"amenity": "dentist"},
    )


def test_descoberta_enfileira_analise(
    londrina, fonte, monkeypatch, django_capture_on_commit_callbacks
):
    """As empresas descobertas entram na fila — uma task por empresa."""
    from apps.analysis import tasks

    enfileiradas = []
    monkeypatch.setattr(tasks.scan_company_task, "delay", lambda cid: enfileiradas.append(cid))

    with django_capture_on_commit_callbacks(execute=True):
        _varrer(londrina, fonte)

    assert len(enfileiradas) == Company.objects.count() == 4


def test_a_task_so_dispara_depois_do_commit(
    londrina, fonte, monkeypatch, django_capture_on_commit_callbacks
):
    """A armadilha: enfileirar dentro da transação faz a task não achar a empresa.

    O bug é intermitente — só aparece quando o worker é rápido o bastante — e é dos que
    somem quando se vai investigar. `on_commit` é o que o impede.
    """
    from apps.analysis import tasks

    visiveis_no_disparo = []

    def espiar(company_id):
        visiveis_no_disparo.append(Company.objects.filter(pk=company_id).exists())

    monkeypatch.setattr(tasks.scan_company_task, "delay", espiar)

    with django_capture_on_commit_callbacks(execute=True):
        _varrer(londrina, fonte)

    assert visiveis_no_disparo and all(
        visiveis_no_disparo
    ), "task disparada antes do COMMIT: a empresa ainda não existia para o worker"


@override_settings(ANALYSIS_AUTO_SCAN_ON_DISCOVERY=False)
def test_pode_ser_desligado(londrina, fonte, monkeypatch, django_capture_on_commit_callbacks):
    from apps.analysis import tasks

    enfileiradas = []
    monkeypatch.setattr(tasks.scan_company_task, "delay", lambda cid: enfileiradas.append(cid))

    with django_capture_on_commit_callbacks(execute=True):
        _varrer(londrina, fonte)

    assert enfileiradas == []


def test_task_de_empresa_sumida_nao_quebra(db):
    import uuid

    from apps.analysis.tasks import scan_company_task, scan_website_task

    assert scan_company_task(str(uuid.uuid4())) == "ignorado"
    assert scan_website_task(str(uuid.uuid4())) == "ignorado"


def test_empresa_sem_site_e_marcada_pela_task(db):
    from apps.analysis.tasks import scan_company_task

    empresa = Company.objects.create(name="Sem site")

    assert scan_company_task(str(empresa.pk)) == "sem site"

    empresa.refresh_from_db()
    assert empresa.website_status == Company.WebsiteStatus.NOT_FOUND
    assert WebsiteScan.objects.count() == 0
