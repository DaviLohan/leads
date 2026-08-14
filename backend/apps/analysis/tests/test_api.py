"""A API de análise.

O endpoint de reanálise dispara uma saída para a rede num endereço que o usuário influencia
— por isso tem papel mínimo e escopo de throttle próprio.
"""

import uuid

import pytest

from apps.accounts.models import Role
from apps.analysis.models import WebsiteFinding, WebsiteScan
from apps.companies.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture
def vendedor(make_user, make_member, org):
    user = make_user("vendedor@exemplo.com")
    make_member(user, org, role=Role.SALES)
    return user


@pytest.fixture
def leitor(make_user, make_member, org):
    user = make_user("leitor@exemplo.com")
    make_member(user, org, role=Role.VIEWER)
    return user


@pytest.fixture
def scan(db):
    empresa = Company.objects.create(name="Clínica São José")
    s = WebsiteScan.objects.create(
        company=empresa, status=WebsiteScan.Status.OK, http_status=200, is_https=False
    )
    WebsiteFinding.objects.create(
        scan=s, code=WebsiteFinding.Code.NO_HTTPS, severity=WebsiteFinding.Severity.HIGH
    )
    return s


def test_anonimo_nao_le(api, scan):
    assert api.get("/api/v1/analysis/scans/").status_code == 403


def test_lista_com_os_achados(api, login_as, leitor, scan):
    """Diagnóstico é dado público sobre a empresa (ADR-0007): leitor enxerga."""
    login_as(leitor)
    resposta = api.get("/api/v1/analysis/scans/")

    assert resposta.status_code == 200
    item = resposta.data["results"][0]
    assert item["company_name"] == "Clínica São José"
    assert item["findings"][0]["code"] == WebsiteFinding.Code.NO_HTTPS
    assert item["findings"][0]["code_label"] == "Site sem HTTPS"


def test_filtra_por_situacao(api, login_as, leitor, scan):
    login_as(leitor)
    assert api.get("/api/v1/analysis/scans/", {"is_https": "false"}).data["count"] == 1
    assert api.get("/api/v1/analysis/scans/", {"is_https": "true"}).data["count"] == 0


def test_leitor_nao_dispara_reanalise(api, login_as, leitor, scan):
    """Sai para a rede num endereço influenciado pelo usuário — não é ação de leitor."""
    login_as(leitor)
    resposta = api.post(f"/api/v1/analysis/scans/companies/{scan.company_id}/")
    assert resposta.status_code == 403


def test_vendedor_dispara_reanalise(api, login_as, vendedor, scan, monkeypatch):
    from apps.analysis import views

    enfileiradas = []
    monkeypatch.setattr(views.scan_company_task, "delay", lambda cid: enfileiradas.append(cid))
    login_as(vendedor)

    resposta = api.post(f"/api/v1/analysis/scans/companies/{scan.company_id}/")

    assert resposta.status_code == 202
    assert enfileiradas == [str(scan.company_id)]


def test_empresa_inexistente_e_404(api, login_as, vendedor):
    login_as(vendedor)
    assert api.post(f"/api/v1/analysis/scans/companies/{uuid.uuid4()}/").status_code == 404


def test_api_e_somente_leitura(api, login_as, vendedor, scan):
    login_as(vendedor)
    assert api.post("/api/v1/analysis/scans/", {}, format="json").status_code == 405
