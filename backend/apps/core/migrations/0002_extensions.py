"""Extensões do PostgreSQL exigidas pela arquitetura (ADR-0002).

- `postgis`: tipos e índices geográficos. O banco de teste é criado do zero, então a
  extensão precisa vir de migration — não basta existir no banco de desenvolvimento.
- `pg_trgm`: similaridade de nome na deduplicação (Etapa 6). É criada agora porque
  extensão é infraestrutura de banco, não regra de negócio, e criá-la depois em uma base
  grande custa mais.

Em backends que não são PostgreSQL estas operações são ignoradas.
"""

from django.contrib.postgres.operations import CreateExtension, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        CreateExtension("postgis"),
        TrigramExtension(),
    ]
