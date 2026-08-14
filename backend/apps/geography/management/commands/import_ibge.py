"""Popula estados e municípios a partir do IBGE.

    python manage.py import_ibge                  # baixa da API
    python manage.py import_ibge --file base.json # lê de arquivo, sem rede

Rodar de novo é seguro: o código IBGE é único no banco, então reimportar atualiza nomes e
não duplica linhas.

O arquivo de `--file` tem o formato `{"estados": [...], "municipios": [...]}`, com os itens
exatamente como a API devolve. Serve para ambiente sem saída para a internet e para
congelar uma versão da base.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.geography import ibge
from apps.geography.services import GeographyImportError, import_cities, import_states


class Command(BaseCommand):
    help = "Importa estados e municípios do IBGE."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            type=Path,
            help='JSON local com as chaves "estados" e "municipios", em vez da API.',
        )

    def handle(self, *args, **options) -> None:
        path: Path | None = options["file"]

        if path is None:
            self.stdout.write("Baixando do IBGE…")
            states_payload = ibge.fetch_states()
            cities_payload = ibge.fetch_cities()
        else:
            states_payload, cities_payload = self._read(path)

        try:
            states = import_states(states_payload)
            cities = import_cities(cities_payload)
        except (GeographyImportError, KeyError, TypeError) as exc:
            # Transação já desfeita pelo `atomic` dos serviços: o banco não ficou pela metade.
            raise CommandError(f"Importação abortada: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Estados: {states.created} novos, {states.updated} atualizados. "
                f"Municípios: {cities.created} novos, {cities.updated} atualizados."
            )
        )

    def _read(self, path: Path) -> tuple[list, list]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Não consegui ler {path}: {exc}") from exc

        if not isinstance(payload, dict) or "estados" not in payload or "municipios" not in payload:
            raise CommandError('O arquivo precisa ser um objeto com "estados" e "municipios".')

        return payload["estados"], payload["municipios"]
