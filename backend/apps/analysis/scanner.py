"""Orquestra a análise: guard → busca → sinais → achados → persistência.

Todo acesso à rede passa por `ssrf.safe_get`. Se um dia aparecer `urlopen` ou `requests`
neste app, o guard virou decoração.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from apps.analysis import html_signals
from apps.analysis.models import WebsiteFinding, WebsiteScan
from apps.analysis.ssrf import FetchError, SSRFBlockedError, safe_get
from apps.companies.models import Company, CompanyWebsite

logger = logging.getLogger(__name__)


def scan_website(website: CompanyWebsite) -> WebsiteScan:
    """Analisa um site e grava o resultado. Nunca levanta: falha vira `WebsiteScan`.

    O erro é dado, não exceção: uma empresa cujo site caiu precisa aparecer como "fora do ar"
    na tela, e não sumir do relatório porque a task morreu.
    """
    try:
        resposta = safe_get(website.url)
    except SSRFBlockedError as exc:
        # Evento de segurança, não indisponibilidade. Fica em WARNING e com status próprio.
        logger.warning(
            "Destino recusado pelo guard de SSRF",
            extra={"website": str(website.pk), "url": website.url, "motivo": str(exc)},
        )
        return _gravar_falha(
            website,
            WebsiteScan.Status.BLOCKED,
            str(exc),
            WebsiteFinding.Code.BLOCKED_TARGET,
            WebsiteFinding.Severity.HIGH,
        )
    except FetchError as exc:
        return _gravar_falha(
            website,
            WebsiteScan.Status.UNREACHABLE,
            str(exc),
            WebsiteFinding.Code.SITE_OFFLINE,
            WebsiteFinding.Severity.HIGH,
        )

    sinais = html_signals.extract(resposta.text)

    with transaction.atomic():
        scan = WebsiteScan.objects.create(
            company=website.company,
            website=website,
            status=WebsiteScan.Status.OK,
            final_url=resposta.final_url[:500],
            http_status=resposta.status,
            is_https=resposta.is_https,
            has_valid_cert=resposta.has_valid_cert,
            response_time_ms=resposta.elapsed_ms,
            redirect_count=resposta.redirect_count,
            title=sinais.title,
            meta_description=sinais.meta_description,
            has_viewport=sinais.has_viewport,
            has_contact_form=sinais.has_contact_form,
            has_whatsapp=sinais.has_whatsapp,
            has_booking=sinais.has_booking,
            has_cart=sinais.has_cart,
            signals={
                "form_count": sinais.form_count,
                "truncated": resposta.truncated,
                "chain": resposta.chain,
                **sinais.extras,
            },
        )
        _registrar_achados(scan, resposta)

        # A visita confirma o que a fonte só sugeria.
        website.status = (
            CompanyWebsite.Status.ONLINE
            if 200 <= resposta.status < 400
            else CompanyWebsite.Status.OFFLINE
        )
        website.last_checked_at = scan.scanned_at
        website.save(update_fields=["status", "last_checked_at", "updated_at"])

    return scan


def _registrar_achados(scan: WebsiteScan, resposta) -> None:
    """Traduz o observado em achados. Observação, nunca julgamento comercial."""
    achados: list[tuple[str, str, str, dict]] = []

    if not scan.is_https:
        achados.append(
            (
                WebsiteFinding.Code.NO_HTTPS,
                WebsiteFinding.Severity.HIGH,
                "O site responde em HTTP puro. Navegador marca como 'não seguro'.",
                {"final_url": scan.final_url},
            )
        )
    if not scan.has_viewport:
        achados.append(
            (
                WebsiteFinding.Code.NO_VIEWPORT,
                WebsiteFinding.Severity.HIGH,
                "Sem meta viewport: a página não se adapta à tela do celular.",
                {},
            )
        )
    if scan.response_time_ms and scan.response_time_ms > settings.WEBSITE_SCAN_SLOW_MS:
        achados.append(
            (
                WebsiteFinding.Code.SLOW_RESPONSE,
                WebsiteFinding.Severity.MEDIUM,
                f"Resposta em {scan.response_time_ms} ms.",
                {"ms": scan.response_time_ms, "limite": settings.WEBSITE_SCAN_SLOW_MS},
            )
        )
    if not scan.has_contact_form and not scan.has_whatsapp:
        achados.append(
            (
                WebsiteFinding.Code.NO_CONTACT_CHANNEL,
                WebsiteFinding.Severity.HIGH,
                "Nenhum formulário de contato nem link de WhatsApp na página inicial.",
                {},
            )
        )
    if not scan.has_booking:
        achados.append(
            (
                WebsiteFinding.Code.NO_BOOKING,
                WebsiteFinding.Severity.MEDIUM,
                "Sem agendamento online identificado.",
                {},
            )
        )
    if resposta.redirect_count >= settings.WEBSITE_SCAN_MAX_REDIRECTS:
        achados.append(
            (
                WebsiteFinding.Code.EXCESSIVE_REDIRECTS,
                WebsiteFinding.Severity.LOW,
                f"{resposta.redirect_count} redirects até a página final.",
                {"chain": resposta.chain},
            )
        )

    WebsiteFinding.objects.bulk_create(
        [
            WebsiteFinding(scan=scan, code=c, severity=s, detail=d, evidence=e)
            for c, s, d, e in achados
        ]
    )


def _gravar_falha(
    website: CompanyWebsite, status: str, detalhe: str, codigo: str, severidade: str
) -> WebsiteScan:
    with transaction.atomic():
        scan = WebsiteScan.objects.create(
            company=website.company, website=website, status=status, error_detail=detalhe[:2000]
        )
        WebsiteFinding.objects.create(
            scan=scan, code=codigo, severity=severidade, detail=detalhe[:2000]
        )
        website.status = CompanyWebsite.Status.OFFLINE
        website.last_checked_at = scan.scanned_at
        website.save(update_fields=["status", "last_checked_at", "updated_at"])
    return scan


def scan_company(company: Company) -> WebsiteScan | None:
    """Analisa o site principal da empresa. Sem site, fecha o `website_status`.

    Fecha a lacuna aberta na Etapa 7: até aqui, empresa sem domínio ficava em `NOT_CHECKED`
    para sempre e ninguém nunca marcava `NOT_FOUND`.

    O scanner **não adivinha domínio**. `nomedaempresa.com.br` pode ser de terceiro,
    parqueado ou de homônimo — e um diagnóstico construído sobre o site errado mente
    inteiro, inclusive na oportunidade que a Etapa 10 calcularia em cima dele.
    """
    site = company.websites.filter(is_primary=True).first() or company.websites.first()

    if site is None:
        if company.website_status != Company.WebsiteStatus.NOT_FOUND:
            company.website_status = Company.WebsiteStatus.NOT_FOUND
            company.save(update_fields=["website_status", "updated_at"])
        # Empresa sem site é o caso de maior valor comercial — não pode ficar de fora só
        # porque não houve o que visitar.
        _detectar_oportunidades(company)
        return None

    scan = scan_website(site)

    # `Company.website_status` responde "a fonte identificou um site?"; `WebsiteScan.status`
    # responde "o site funciona?". São perguntas diferentes e ficam em campos diferentes.
    #
    # Site que não resolve mais (tag velha do OSM, domínio expirado) continua FOUND: **foi**
    # identificado. Rebaixar para NOT_FOUND faria o rótulo mentir na outra direção — ele diz
    # "não identificado nas fontes", e a fonte identificou.
    #
    # Para o produto isso não se perde: a Etapa 10 lê o `WebsiteScan`, e site inalcançável é
    # justamente uma das oportunidades mais fortes.
    situacao = (
        Company.WebsiteStatus.FOUND
        if scan.status == WebsiteScan.Status.OK
        else company.website_status
    )
    if company.website_status != situacao:
        company.website_status = situacao
        company.save(update_fields=["website_status", "updated_at"])

    _detectar_oportunidades(company)
    return scan


def _detectar_oportunidades(company: Company) -> None:
    """Reavalia as oportunidades logo depois de analisar.

    Import local: `opportunities` importa `models` deste mesmo app, e no topo isto seria
    ciclo. Falha aqui não pode desfazer a análise, que é o dado caro — a varredura já
    aconteceu, e perdê-la por causa do motor de regras seria trocar o certo pelo duvidoso.
    """
    from apps.analysis.opportunities import detect

    try:
        detect(company)
    except Exception:
        logger.exception("Falha ao detectar oportunidades", extra={"company": str(company.pk)})
