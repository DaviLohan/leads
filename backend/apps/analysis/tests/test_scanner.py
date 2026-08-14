"""O scanner: sinais extraídos, achados registrados, falha virando dado.

Sem rede: `safe_get` é dublado. O guard já tem seus próprios testes em `test_ssrf.py`.
"""

import pytest

from apps.analysis import scanner
from apps.analysis.models import WebsiteFinding, WebsiteScan
from apps.analysis.ssrf import FetchError, SafeResponse, SSRFBlockedError
from apps.companies.models import Company, CompanyWebsite

pytestmark = pytest.mark.django_db


PAGINA_COMPLETA = """
<html><head>
  <title>Clínica São José</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Odontologia em Londrina">
</head><body>
  <a href="https://wa.me/554333241000">Fale no WhatsApp</a>
  <a href="https://calendly.com/saojose">Agende sua consulta</a>
  <form action="/contato"><input name="email"><textarea name="mensagem"></textarea></form>
</body></html>
"""

PAGINA_POBRE = (
    "<html><head><title>Loja</title></head><body><p>Telefone: 3324-1000</p></body></html>"
)


@pytest.fixture
def site(db):
    empresa = Company.objects.create(name="Clínica São José")
    return CompanyWebsite.objects.create(
        company=empresa, url="https://exemplo.com.br", domain="exemplo.com.br", is_primary=True
    )


def _resposta(corpo=PAGINA_COMPLETA, **kwargs):
    padrao = {
        "final_url": "https://exemplo.com.br/",
        "status": 200,
        "headers": {"content-type": "text/html"},
        "body": corpo.encode(),
        "is_https": True,
        "has_valid_cert": True,
        "elapsed_ms": 300,
    }
    return SafeResponse(**{**padrao, **kwargs})


class TestSinais:
    def test_extrai_tudo_de_uma_pagina_completa(self, site, monkeypatch):
        monkeypatch.setattr(scanner, "safe_get", lambda url: _resposta())

        scan = scanner.scan_website(site)

        assert scan.status == WebsiteScan.Status.OK
        assert scan.title == "Clínica São José"
        assert scan.meta_description == "Odontologia em Londrina"
        assert (scan.has_viewport, scan.has_whatsapp, scan.has_booking, scan.has_contact_form) == (
            True,
            True,
            True,
            True,
        )

    def test_pagina_pobre_nao_inventa_sinal(self, site, monkeypatch):
        monkeypatch.setattr(scanner, "safe_get", lambda url: _resposta(PAGINA_POBRE))

        scan = scanner.scan_website(site)

        assert scan.has_viewport is False
        assert scan.has_whatsapp is False
        assert scan.has_contact_form is False

    def test_html_quebrado_nao_derruba_a_analise(self, site, monkeypatch):
        """Site de pequeno negócio vem torto o tempo todo — perder um sinal, sim; o scan, não."""
        monkeypatch.setattr(
            scanner, "safe_get", lambda url: _resposta("<html><title>X</title><div><p></html")
        )

        assert scanner.scan_website(site).status == WebsiteScan.Status.OK

    def test_formulario_de_busca_nao_conta_como_contato(self, site, monkeypatch):
        html = '<html><body><form><input name="q" placeholder="Buscar"></form></body></html>'
        monkeypatch.setattr(scanner, "safe_get", lambda url: _resposta(html))

        assert scanner.scan_website(site).has_contact_form is False


class TestAchados:
    def test_site_sem_https_gera_achado_alto(self, site, monkeypatch):
        monkeypatch.setattr(
            scanner, "safe_get", lambda url: _resposta(PAGINA_POBRE, is_https=False)
        )

        scan = scanner.scan_website(site)
        achado = scan.findings.get(code=WebsiteFinding.Code.NO_HTTPS)
        assert achado.severity == WebsiteFinding.Severity.HIGH

    def test_pagina_completa_nao_gera_achado_de_contato_nem_agendamento(self, site, monkeypatch):
        monkeypatch.setattr(scanner, "safe_get", lambda url: _resposta())

        codigos = set(scanner.scan_website(site).findings.values_list("code", flat=True))
        assert WebsiteFinding.Code.NO_CONTACT_CHANNEL not in codigos
        assert WebsiteFinding.Code.NO_BOOKING not in codigos
        assert WebsiteFinding.Code.NO_VIEWPORT not in codigos

    def test_pagina_pobre_gera_a_lista_toda(self, site, monkeypatch):
        monkeypatch.setattr(
            scanner, "safe_get", lambda url: _resposta(PAGINA_POBRE, is_https=False)
        )

        codigos = set(scanner.scan_website(site).findings.values_list("code", flat=True))
        assert codigos >= {
            WebsiteFinding.Code.NO_HTTPS,
            WebsiteFinding.Code.NO_VIEWPORT,
            WebsiteFinding.Code.NO_CONTACT_CHANNEL,
            WebsiteFinding.Code.NO_BOOKING,
        }

    def test_resposta_lenta(self, site, monkeypatch):
        monkeypatch.setattr(scanner, "safe_get", lambda url: _resposta(elapsed_ms=9000))

        assert (
            scanner.scan_website(site)
            .findings.filter(code=WebsiteFinding.Code.SLOW_RESPONSE)
            .exists()
        )


class TestFalhas:
    def test_site_fora_do_ar_vira_dado_e_nao_excecao(self, site, monkeypatch):
        """Empresa com site caído precisa aparecer no relatório, não sumir dele."""

        def explodir(url):
            raise FetchError("connection refused")

        monkeypatch.setattr(scanner, "safe_get", explodir)

        scan = scanner.scan_website(site)

        assert scan.status == WebsiteScan.Status.UNREACHABLE
        assert scan.findings.get().code == WebsiteFinding.Code.SITE_OFFLINE
        site.refresh_from_db()
        assert site.status == CompanyWebsite.Status.OFFLINE

    def test_destino_recusado_nao_se_disfarca_de_site_fora_do_ar(self, site, monkeypatch):
        """`BLOCKED` é evento de segurança. Virar `UNREACHABLE` esconderia um SSRF."""

        def bloquear(url):
            raise SSRFBlockedError("127.0.0.1 é loopback")

        monkeypatch.setattr(scanner, "safe_get", bloquear)

        scan = scanner.scan_website(site)

        assert scan.status == WebsiteScan.Status.BLOCKED
        assert scan.status != WebsiteScan.Status.UNREACHABLE
        assert scan.findings.get().code == WebsiteFinding.Code.BLOCKED_TARGET


class TestSituacaoDoSite:
    def test_empresa_sem_site_recebe_not_found(self, db):
        """Fecha a lacuna da Etapa 7: ninguém marcava NOT_FOUND."""
        empresa = Company.objects.create(name="Sem site")
        assert empresa.website_status == Company.WebsiteStatus.NOT_CHECKED

        assert scanner.scan_company(empresa) is None

        empresa.refresh_from_db()
        assert empresa.website_status == Company.WebsiteStatus.NOT_FOUND

    def test_not_found_usa_o_rotulo_obrigatorio(self, db):
        """Afirmar que a empresa não tem site é proibido (CLAUDE.md)."""
        empresa = Company.objects.create(name="Sem site")
        scanner.scan_company(empresa)
        empresa.refresh_from_db()

        assert (
            str(empresa.get_website_status_display())
            == "Site oficial não identificado nas fontes analisadas"
        )

    def test_nao_adivinha_dominio(self, db, monkeypatch):
        """Adivinhar produziria diagnóstico sobre o site de outra empresa."""
        chamou = []
        monkeypatch.setattr(scanner, "safe_get", lambda url: chamou.append(url))

        scanner.scan_company(Company.objects.create(name="Padaria Central"))

        assert chamou == [], "o scanner tentou buscar alguma URL para empresa sem site"

    def test_site_analisado_com_sucesso_marca_found(self, site, monkeypatch):
        monkeypatch.setattr(scanner, "safe_get", lambda url: _resposta())

        scanner.scan_company(site.company)

        site.company.refresh_from_db()
        assert site.company.website_status == Company.WebsiteStatus.FOUND

    def test_prefere_o_site_principal(self, site, monkeypatch):
        CompanyWebsite.objects.create(
            company=site.company, url="https://outro.com.br", domain="outro.com.br"
        )
        buscadas = []
        monkeypatch.setattr(scanner, "safe_get", lambda url: buscadas.append(url) or _resposta())

        scanner.scan_company(site.company)

        assert buscadas == ["https://exemplo.com.br"]


def test_site_inalcancavel_nao_rebaixa_a_situacao_da_empresa(site, monkeypatch):
    """Identificação e alcançabilidade são perguntas diferentes, em campos diferentes.

    Domínio expirado numa tag velha do OSM continua tendo sido identificado. Rebaixar para
    NOT_FOUND faria o rótulo "não identificado nas fontes" mentir — a fonte identificou.
    O fato de o site não funcionar fica no `WebsiteScan`, que é quem a Etapa 10 vai ler.
    """
    site.company.website_status = Company.WebsiteStatus.FOUND
    site.company.save()

    def explodir(url):
        raise FetchError("Name or service not known")

    monkeypatch.setattr(scanner, "safe_get", explodir)

    scan = scanner.scan_company(site.company)
    site.company.refresh_from_db()

    assert scan.status == WebsiteScan.Status.UNREACHABLE
    assert site.company.website_status == Company.WebsiteStatus.FOUND
