"""Dados de desenvolvimento.

Nunca depende de API externa nem de rede (CLAUDE.md). Cresce a cada etapa: por enquanto
cria a organização de desenvolvimento com seu proprietário. Recusa rodar fora de DEBUG.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Membership, Organization, Role
from apps.accounts.services import create_organization_with_owner

# Categorias mínimas para o Radar funcionar, com a tradução para as tags do OSM. É o
# `provider_mapping` (Etapa 5) que evita categoria hardcoded dentro do provider.
CATEGORIAS = [
    ("dentistas", "Dentistas", {"osm-overpass": {"amenity": "dentist"}}),
    ("padarias", "Padarias", {"osm-overpass": {"shop": "bakery"}}),
    ("restaurantes", "Restaurantes", {"osm-overpass": {"amenity": "restaurant"}}),
    ("farmacias", "Farmácias", {"osm-overpass": {"amenity": "pharmacy"}}),
    ("academias", "Academias", {"osm-overpass": {"leisure": "fitness_centre"}}),
    ("veterinarias", "Veterinárias", {"osm-overpass": {"amenity": "veterinary"}}),
    ("oficinas", "Oficinas mecânicas", {"osm-overpass": {"shop": "car_repair"}}),
    ("saloes", "Salões de beleza", {"osm-overpass": {"shop": "hairdresser"}}),
]

DEV_ORG = "Organização de Desenvolvimento"
DEV_EMAIL = "admin@leads.local"
DEV_PASSWORD = "admin-dev-12345"  # noqa: S105 - credencial local, só com DEBUG=True


class Command(BaseCommand):
    help = "Cria dados fictícios para desenvolvimento."

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_dev_data só roda com DEBUG=True.")

        self._categorias()

        if Organization.objects.filter(name=DEV_ORG).exists():
            self.stdout.write(f"Organização de desenvolvimento já existe. Login: {DEV_EMAIL}")
            return

        organization, user = create_organization_with_owner(
            name=DEV_ORG,
            owner_email=DEV_EMAIL,
            owner_password=DEV_PASSWORD,
            owner_full_name="Admin Dev",
        )
        # Acesso ao admin do Django em desenvolvimento.
        user_model = get_user_model()
        user_model.objects.filter(pk=user.pk).update(is_staff=True, is_superuser=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Organização '{organization.name}' criada.\n"
                f"Login: {DEV_EMAIL} / {DEV_PASSWORD}\n"
                f"Papel: {Membership.objects.get(user=user).role} ({Role.OWNER.label})"
            )
        )

    def _categorias(self) -> None:
        """Idempotente: reexecutar não duplica nem sobrescreve o que foi ajustado à mão."""
        from apps.companies.models import Category

        for slug, nome, mapeamento in CATEGORIAS:
            Category.objects.get_or_create(
                slug=slug, defaults={"name": nome, "provider_mapping": mapeamento}
            )
        self.stdout.write(f"Categorias: {Category.objects.count()}")
