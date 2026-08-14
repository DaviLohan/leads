"""Cadastra as regras de pontuação. Idempotente.

Ambiente sem regras produz score 0, não erro (ADR-0008). `get_or_create` para não
sobrescrever peso ajustado pelo admin — que é justamente o motivo de isso viver no banco.

Os pesos abaixo são o ponto de partida, não a verdade: quem vende é que sabe se "sem site"
vale 30 ou 40, e ajustar é UPDATE.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

REGRAS: list[dict[str, Any]] = [
    {
        "code": "sem_site",
        "name": "Sem site identificado",
        "points": 35,
        "reason_template": "Nenhum site oficial identificado nas fontes analisadas.",
    },
    {
        "code": "site_fora_do_ar",
        "name": "Site fora do ar",
        "points": 30,
        "reason_template": "O endereço identificado não responde: domínio ou hospedagem fora.",
    },
    {
        "code": "site_nao_responsivo",
        "name": "Site não adaptado ao celular",
        "points": 20,
        "reason_template": "A página não se adapta à tela do celular.",
    },
    {
        "code": "site_sem_https",
        "name": "Site sem HTTPS",
        "points": 15,
        "reason_template": "O navegador marca o site como 'não seguro'.",
    },
    {
        "code": "sem_canal_de_contato",
        "name": "Sem canal de contato no site",
        "points": 15,
        "reason_template": "Quem chega pelo site não consegue falar com a empresa.",
    },
    {
        "code": "sem_agendamento",
        "name": "Sem agendamento online",
        "points": 10,
        "reason_template": "Não há como marcar horário pela internet.",
    },
    {
        "code": "site_lento",
        "name": "Site lento",
        "points": 10,
        "params": {"threshold_ms": 3000},
        "reason_template": "O site demora a responder em conexão móvel.",
    },
    {
        "code": "sem_whatsapp",
        "name": "Sem WhatsApp no site",
        "points": 5,
        "reason_template": "O canal comercial mais usado no Brasil não está no site.",
    },
    {
        # Negativo de propósito: mede dificuldade de abordagem, não qualidade da empresa.
        # Sem telefone nem e-mail, não há por onde começar a conversa — e um lead que não dá
        # para abordar não pode estar no topo da fila, por melhor que seja a oportunidade.
        "code": "poucos_contatos",
        "name": "Sem contato conhecido",
        "points": -20,
        "params": {"minimo": 1},
        "reason_template": "Nenhum telefone ou e-mail encontrado: não há como abordar.",
    },
]


class Command(BaseCommand):
    help = "Cadastra as regras de pontuação de leads."

    def handle(self, *args, **options) -> None:
        from apps.analysis.models import ScoreRule
        from apps.analysis.rules import REGISTRO

        criadas = 0
        for dados in REGRAS:
            # Falha alto: regra apontando para predicado inexistente nunca pontuaria, e o
            # score baixo pareceria "empresa ruim" em vez de "seed errado".
            if dados["code"] not in REGISTRO:
                self.stderr.write(f"Predicado desconhecido: {dados['code']}")
                continue
            _, nova = ScoreRule.objects.get_or_create(code=dados["code"], defaults=dados)
            criadas += nova

        ativas = ScoreRule.objects.filter(is_active=True)
        teto = sum(r.points for r in ativas if r.points > 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"Regras de pontuação: {criadas} novas, {ativas.count()} ativas. "
                f"Máximo teórico antes do corte: {teto}."
            )
        )
