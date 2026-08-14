# ADR-0002 — PostgreSQL + PostGIS como fonte de verdade

**Status:** aceito · 2026-08-13

## Contexto

O produto precisa de: integridade forte (empresa não pode duplicar), busca por similaridade de
nome em escala, consultas geográficas (raio, proximidade, particionamento por município) e
campos semiestruturados (payload bruto do provider, evidências de análise).

Adicionar PostGIS depois exigiria migração de tipo de coluna e reindexação em tabelas grandes —
caro justamente quando o volume já existir.

## Decisão

PostgreSQL 16 com PostGIS 3.4 desde o primeiro dia, via `django.contrib.gis`.

- `PointField` (SRID 4326) para localização de empresa e centroide de município; índice GiST.
- `pg_trgm` + índice GIN para similaridade de nome na deduplicação.
- `JSONField` para payload bruto e evidências — dado que não é consultado por coluna.
- Constraints de integridade no banco (`UniqueConstraint`, `CheckConstraint`, FK), não só na
  aplicação.
- Dinheiro em `DecimalField`. Datas com timezone, armazenadas em UTC.

Redis é cache, broker, rate limit e lock distribuído — **nunca** fonte de verdade. Perder o
Redis pode custar desempenho e jobs em voo; não pode custar dado.

## Consequências

- **Bom:** um banco só resolve relacional, geográfico, texto e semiestruturado. Dedup e
  particionamento geográfico ficam viáveis em milhões de linhas.
- **Ruim:** a imagem do backend precisa de GDAL/GEOS/PROJ (build maior, ~150 MB a mais), e a
  imagem do banco é `postgis/postgis` em vez da oficial. Migrations com extensão exigem
  `CreateExtension` explícito.
- **Custo aceito:** pagar o peso do PostGIS agora é mais barato que migrar depois.

## Alternativas rejeitadas

- **PostgreSQL sem PostGIS, com lat/lng em float** — não indexa proximidade de forma eficiente e
  transforma toda consulta por raio em varredura.
- **Elasticsearch para busca/dedup** — segundo sistema para manter em sincronia, sem ganho que
  `pg_trgm` não entregue nesta fase.
- **MongoDB** — o modelo é fortemente relacional (empresa ↔ fontes ↔ leads ↔ interações) e a
  integridade é requisito central.
