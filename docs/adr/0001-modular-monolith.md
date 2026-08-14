# ADR-0001 — Monólito modular

**Status:** aceito · 2026-08-13

## Contexto

A plataforma tem domínios bem distintos (descoberta, análise de sites, scoring, CRM) e vai
crescer por anos, podendo chegar a milhões de empresas. Há tentação de já nascer distribuída.

Mas o time é pequeno, o produto ainda não tem tráfego, e nenhum dos domínios tem requisito de
escala ou disponibilidade independente comprovado. Microserviços cobrariam agora — rede,
deploy, observabilidade distribuída, consistência eventual — por um benefício futuro incerto.

## Decisão

Monólito modular Django, com fronteiras de domínio explícitas por app e regra de dependência
unidirecional. Deploy único (web + workers Celery a partir da mesma imagem).

Fica **fora** até haver necessidade comprovada e novo ADR: Kubernetes, Kafka, microserviços,
event sourcing, CQRS, service mesh, GraphQL.

As fronteiras são desenhadas para que Discovery Worker, Website Scanner, AI Service e Analytics
possam ser extraídos depois — a comunicação entre eles já é assíncrona via fila.

## Consequências

- **Bom:** um `docker compose up` sobe tudo; refatorar entre domínios é barato; transação
  atômica cruzando domínios continua possível; onboarding simples.
- **Ruim:** disciplina de fronteira é responsabilidade humana — import circular é o sintoma de
  que alguém a quebrou. Escalar significa escalar o processo inteiro (mitigado por workers
  Celery separados por fila).
- **Sinais para revisitar:** uma fila dominando recurso do resto, deploy travado por um domínio,
  ou necessidade real de linguagem/runtime diferente.

## Alternativas rejeitadas

- **Microserviços desde o início** — custo operacional imediato sem problema real que justifique.
- **Serverless / funções** — jobs longos de coleta e varredura não se encaixam bem, e amarra a
  um fornecedor cloud (contraria o requisito de portabilidade).
- **App Django única sem divisão** — vira bola de barro; a modularização é justamente o que
  permite extrair serviços depois.
