# Deploy

## Princípio

A aplicação é containerizada e não depende de nenhum fornecedor cloud específico. Roda em VPS,
AWS, GCP, Azure, DigitalOcean, Hetzner, Railway — qualquer host compatível com containers.
Nenhum serviço gerenciado proprietário faz parte do caminho crítico.

## Ambientes

| Ambiente | Settings | Características |
|---|---|---|
| development | `config.settings.development` | `DEBUG=True`, CORS liberado para localhost, e-mail no console |
| test | `config.settings.test` | Banco efêmero, Celery síncrono, hasher rápido, cache local |
| staging | `config.settings.production` | Igual à produção, dados próprios, domínio próprio |
| production | `config.settings.production` | `DEBUG=False`, HSTS, cookies `Secure`, CORS restrito |

`DEBUG=True` em produção é impossível por construção: `production.py` fixa `DEBUG = False`.

## Variáveis obrigatórias em produção

| Variável | Observação |
|---|---|
| `DJANGO_SECRET_KEY` | Obrigatória. A aplicação **falha ao iniciar** se ausente ou igual ao valor de dev |
| `DJANGO_ALLOWED_HOSTS` | Lista separada por vírgula |
| `DATABASE_URL` | `postgis://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://host:6379/0` |
| `CORS_ALLOWED_ORIGINS` | Origens exatas. Nunca `*` |
| `CSRF_TRUSTED_ORIGINS` | Com esquema: `https://app.exemplo.com` |
| `SENTRY_DSN` | Opcional |

Segredos vêm do secret manager do host ou de variáveis de ambiente injetadas no deploy. Nunca do
repositório.

## Subindo

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend python manage.py migrate --noinput
docker compose exec backend python manage.py collectstatic --noinput
docker compose exec backend python manage.py check --deploy   # sem avisos críticos
```

Processos: `gunicorn` para o web, `celery worker` e `celery beat` como serviços separados. O
frontend roda `next start` (ou é servido como build estático atrás do proxy).

Um reverse proxy (nginx, Caddy ou o do provedor) termina o TLS e encaminha para o frontend, que
faz o rewrite de `/api/*` para o backend — mantendo a mesma origem exigida pelo ADR-0005.

## Health checks

- `GET /health/live` — o processo está vivo. Não toca em dependência. Use para liveness.
- `GET /health/ready` — Postgres e Redis respondem. Use para readiness e para tirar a instância
  do balanceador durante deploy.

## Escalando

Ordem prática, na medida em que a carga aparecer:

1. Mais réplicas do worker Celery (o gargalo natural é coleta e varredura de sites).
2. Filas separadas por tipo de trabalho, com concorrência própria.
3. Mais réplicas do web.
4. Réplica de leitura do Postgres para relatórios.

Não escale por padrão o que ainda não mediu.

## Backup

**PostgreSQL** — dump lógico diário, com retenção de 30 dias, armazenado **fora** do host da
aplicação (object storage em outro provedor, de preferência):

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > leads-$(date +%F).dump
```

**Redis** — não precisa de backup. É cache, broker e rate limit; perdê-lo custa jobs em voo, não
dado (ADR-0002). Jobs interrompidos são retomáveis pelo estado em `SearchJob`.

## Restore

```bash
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < arquivo.dump
docker compose exec backend python manage.py migrate --noinput
```

**Teste de restore trimestral, obrigatório.** Restaurar o dump mais recente em ambiente separado,
subir a aplicação contra ele e conferir contagens e um fluxo de leitura. Backup que nunca foi
restaurado não conta como backup — só como esperança.

Registrar data e resultado de cada teste.

## Rollback

Imagens são versionadas por tag. Rollback é subir a tag anterior.

Migration é o ponto delicado: prefira mudanças compatíveis para trás (adicionar coluna anulável,
depois popular, depois tornar obrigatória em outro deploy). Assim o rollback da imagem não exige
rollback do schema.

## Observabilidade

- Logs estruturados em JSON com `request_id` no stdout — coletados pelo runtime de container.
- Sentry opcional via `SENTRY_DSN`.
- `ProviderUsage` acompanha requests, quota e custo estimado por provider e período.

## Checklist de primeiro deploy

- [ ] `DJANGO_SECRET_KEY` gerada e guardada no secret manager
- [ ] `DEBUG=False` confirmado (`manage.py check --deploy` limpo)
- [ ] TLS ativo, HSTS respondendo
- [ ] `CORS_ALLOWED_ORIGINS` e `CSRF_TRUSTED_ORIGINS` corretos
- [ ] Migrations aplicadas
- [ ] Backup agendado e **restore testado**
- [ ] Health checks ligados ao balanceador
- [ ] Logs sendo coletados
- [ ] Nenhum segredo no repositório ou no histórico do Git
