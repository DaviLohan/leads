"""Cria o funil padrão de uma organização.

Estágios do PROJECT_PLAN §4: `NEW → ... → WON/LOST` mais `DO_NOT_CONTACT`. Idempotente.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

# (código, nome, encerra?, é ganho?)
ESTAGIOS = [
    ("novo", "Novo", False, False),
    ("contatado", "Contatado", False, False),
    ("qualificado", "Qualificado", False, False),
    ("proposta", "Proposta enviada", False, False),
    ("negociacao", "Em negociação", False, False),
    ("ganho", "Ganho", True, True),
    ("perdido", "Perdido", True, False),
    # Último de propósito: é para onde a supressão manda o lead, e o serviço pega o terminal
    # não-ganho de maior posição.
    ("nao-contatar", "Não contatar", True, False),
]


def criar_funil_padrao(organization):
    """Cria (ou devolve) o funil padrão da organização, com todos os estágios."""
    from apps.crm.models import Pipeline, PipelineStage

    funil, _ = Pipeline.objects.get_or_create(
        organization=organization, is_default=True, defaults={"name": "Funil padrão"}
    )
    for posicao, (codigo, nome, terminal, ganho) in enumerate(ESTAGIOS, start=1):
        PipelineStage.objects.get_or_create(
            pipeline=funil,
            code=codigo,
            defaults={
                "name": nome,
                "position": posicao,
                "is_terminal": terminal,
                "is_won": ganho,
            },
        )
    return funil


class Command(BaseCommand):
    help = "Cria o funil padrão de uma organização."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--organization", help="Slug da organização. Vazio = todas.")

    def handle(self, *args, **options) -> None:
        from apps.accounts.models import Organization

        organizacoes = Organization.objects.all()
        if slug := options.get("organization"):
            organizacoes = organizacoes.filter(slug=slug)
            if not organizacoes.exists():
                raise CommandError(f"Organização {slug!r} não encontrada.")

        for org in organizacoes:
            funil = criar_funil_padrao(org)
            self.stdout.write(f"{org.name}: {funil.name} com {funil.stages.count()} estágios")

        self.stdout.write(self.style.SUCCESS("Funis prontos."))
