"""Tasks de análise. Casca fina: recebe ID, delega a `scanner` (CLAUDE.md)."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.analysis.scanner import scan_company, scan_website
from apps.companies.models import Company, CompanyWebsite

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def scan_website_task(website_id: str) -> str:
    """Analisa um site. Sem retry: `scan_website` transforma falha em `WebsiteScan`.

    Repetir não ajudaria — site fora do ar continua fora do ar, e destino recusado pelo guard
    continua recusado. O reagendamento periódico é da Etapa 14, com intervalo próprio.
    """
    site = CompanyWebsite.objects.filter(pk=website_id).select_related("company").first()
    if site is None:
        logger.info("Site sumiu antes da análise", extra={"website": website_id})
        return "ignorado"

    scan = scan_website(site)
    return scan.status


@shared_task(ignore_result=True)
def scan_company_task(company_id: str) -> str:
    """Analisa a empresa, inclusive para marcar NOT_FOUND quando ela não tem site."""
    empresa = Company.objects.filter(pk=company_id).first()
    if empresa is None:
        return "ignorado"

    scan = scan_company(empresa)
    return scan.status if scan else "sem site"
