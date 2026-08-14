"""Cria a primeira organização e seu proprietário.

Não existe cadastro público (SECURITY.md): a plataforma começa por aqui, e os demais
usuários entram por convite.
"""

from __future__ import annotations

import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.accounts.services import create_organization_with_owner


class Command(BaseCommand):
    help = "Cria uma organização e seu usuário proprietário (OWNER)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--name", required=True, help="Nome da organização")
        parser.add_argument("--owner-email", required=True, help="E-mail do proprietário")
        parser.add_argument("--owner-name", default="", help="Nome completo do proprietário")
        parser.add_argument(
            "--owner-password",
            default=None,
            help="Senha do proprietário. Sem este argumento, é pedida interativamente — "
            "o que evita a senha ficar no histórico do shell.",
        )

    def handle(self, *args, **options) -> None:
        password = options["owner_password"] or getpass.getpass("Senha do proprietário: ")
        if not password:
            raise CommandError("Senha é obrigatória.")

        try:
            organization, user = create_organization_with_owner(
                name=options["name"],
                owner_email=options["owner_email"],
                owner_password=password,
                owner_full_name=options["owner_name"],
            )
        except IntegrityError as exc:
            raise CommandError(f"Não foi possível criar a organização: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Organização '{organization.name}' ({organization.slug}) criada "
                f"com proprietário {user.email}."
            )
        )
