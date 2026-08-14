"""Cadastra as fontes conhecidas. Idempotente: rodar de novo não duplica nem sobrescreve.

A configuração de cada fonte é linha de banco, não constante em código — ligar, desligar ou
afrouxar limite tem de valer sem deploy. Este comando só garante que a linha exista.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.providers.base import RetentionPolicy
from apps.providers.mock import MockProvider
from apps.providers.overpass import OverpassProvider


class Command(BaseCommand):
    help = "Cria as linhas de configuração das fontes de dados."

    def handle(self, *args, **options) -> None:
        from apps.providers.models import Provider

        fontes = [
            {
                "slug": OverpassProvider.slug,
                "name": "OpenStreetMap (Overpass)",
                "retention_policy": RetentionPolicy.PERSIST,
                "rate_limit_per_second": settings.OVERPASS_RATE_LIMIT_PER_SECOND,
                # Teto diário conservador: o endpoint público é comunitário e tem política
                # de uso justo (ADR-0004). Varrer o Brasil contra ele é abuso.
                "daily_quota": settings.OVERPASS_DAILY_QUOTA,
                "config": {"attribution": "© colaboradores do OpenStreetMap"},
            },
            {
                "slug": MockProvider.slug,
                "name": "Fonte fictícia (testes)",
                "retention_policy": RetentionPolicy.PERSIST,
                "rate_limit_per_second": 1000,
                "daily_quota": None,
                # Não fica habilitada por padrão: dado fictício em produção é pior que
                # nenhum dado. Quem quiser usá-la liga de propósito.
                "is_enabled": settings.DEBUG,
            },
        ]

        for dados in fontes:
            _, criada = Provider.objects.get_or_create(slug=dados["slug"], defaults=dados)
            estado = "criada" if criada else "já existia"
            self.stdout.write(f"{dados['slug']}: {estado}")

        self.stdout.write(self.style.SUCCESS("Fontes cadastradas."))
