"""Cadastra os tipos de oportunidade. Idempotente.

O conjunto inicial de regras vem do seed (ADR-0008, seção operacional): ambiente sem regras
cadastradas produz zero oportunidades, não erro. `get_or_create` para não sobrescrever peso
que alguém já ajustou pelo admin — que é justamente o ponto de ter isso no banco.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

# Categorias em que agendamento online é padrão do setor — a ausência é lacuna real, e não
# escolha do negócio. Fora delas, "sem agendamento" não é oportunidade, é normal.
COM_AGENDAMENTO = ["dentistas", "veterinarias", "saloes", "academias"]

TIPOS: list[dict[str, Any]] = [
    {
        "code": "site-institucional",
        "name": "Site institucional",
        "description": (
            "Nenhum site oficial foi identificado nas fontes analisadas. É a oportunidade de "
            "maior valor: a empresa não tem presença própria na internet."
        ),
        "rule_code": "sem_site",
        "base_confidence": "0.90",
    },
    {
        "code": "site-fora-do-ar",
        "name": "Site fora do ar",
        "description": (
            "Existe endereço identificado, mas ele não responde — domínio expirado ou "
            "hospedagem encerrada. Na prática a empresa está sem site, e nem sabe."
        ),
        "rule_code": "site_fora_do_ar",
        "base_confidence": "0.85",
    },
    {
        "code": "migracao-https",
        "name": "Migração para HTTPS",
        "description": "O site responde em HTTP puro; o navegador marca como 'não seguro'.",
        "rule_code": "site_sem_https",
        "base_confidence": "0.95",
    },
    {
        "code": "site-responsivo",
        "name": "Adaptação para celular",
        "description": "Sem meta viewport: a página não se adapta à tela do celular.",
        "rule_code": "site_nao_responsivo",
        "base_confidence": "0.85",
    },
    {
        "code": "otimizacao-desempenho",
        "name": "Otimização de desempenho",
        "description": "O site demora a responder, e demora custa visita em conexão móvel.",
        "rule_code": "site_lento",
        "rule_params": {"threshold_ms": 3000},
        "base_confidence": "0.70",
    },
    {
        "code": "canal-de-contato",
        "name": "Canal de contato no site",
        "description": (
            "Site no ar sem formulário nem WhatsApp: quem chega pela internet não consegue "
            "falar com a empresa."
        ),
        "rule_code": "sem_canal_de_contato",
        "base_confidence": "0.85",
    },
    {
        "code": "agendamento-online",
        "name": "Agendamento online",
        "description": (
            "Setor em que marcar horário pela internet é esperado, e o site não oferece."
        ),
        "rule_code": "sem_agendamento",
        "category_slugs": COM_AGENDAMENTO,
        "base_confidence": "0.75",
    },
    {
        "code": "loja-virtual",
        "name": "Loja virtual",
        "description": "Comércio com site sem carrinho: vende presencialmente, não online.",
        "rule_code": "sem_ecommerce",
        "category_slugs": ["padarias", "restaurantes", "farmacias"],
        "base_confidence": "0.60",
    },
    {
        "code": "contato-digital",
        "name": "Cadastro de contato",
        "description": (
            "Nenhum telefone nem e-mail encontrado. Antes de vender qualquer coisa, é preciso "
            "conseguir falar com a empresa."
        ),
        "rule_code": "poucos_contatos",
        "rule_params": {"minimo": 1},
        "base_confidence": "0.80",
    },
]


class Command(BaseCommand):
    help = "Cadastra os tipos de oportunidade e suas regras."

    def handle(self, *args, **options) -> None:
        from apps.analysis.models import OpportunityType
        from apps.analysis.rules import REGISTRO

        criados = 0
        for dados in TIPOS:
            # Falha alto: tipo apontando para predicado inexistente nunca detectaria nada, e
            # o silêncio pareceria "não há oportunidades" em vez de "o seed está errado".
            if dados["rule_code"] not in REGISTRO:
                self.stderr.write(f"Regra desconhecida: {dados['rule_code']}")
                continue

            _, novo = OpportunityType.objects.get_or_create(code=dados["code"], defaults=dados)
            criados += novo

        total = OpportunityType.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f"Tipos de oportunidade: {criados} novos, {total} no total.")
        )
