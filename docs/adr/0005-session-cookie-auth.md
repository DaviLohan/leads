# ADR-0005 — Autenticação por sessão em cookie HTTPOnly

**Status:** aceito · 2026-08-13

## Contexto

O requisito é explícito: cookies `HttpOnly`, `Secure`, `SameSite` apropriado, e **não** guardar
token sensível em `localStorage`. Também exige logout, troca de senha, sessões e revogação.

JWT em `localStorage` é o padrão mais comum em SPAs e é justamente o que o requisito veta —
qualquer XSS rouba o token, e revogar antes da expiração exige uma blacklist, ou seja, estado no
servidor de novo.

O obstáculo prático de cookie de sessão numa SPA é a origem: frontend em `:3000` e backend em
`:8000` são sites diferentes para o browser, e `SameSite=Lax` bloqueia o envio do cookie.

## Decisão

Sessão do Django em cookie, com `HttpOnly`, `SameSite=Lax` e `Secure` em produção. Proteção CSRF
ativa. Sem JWT.

O obstáculo da origem se resolve com **rewrite no Next.js**: `/api/:path*` é reescrito para o
backend, então o browser enxerga tudo em uma única origem, em dev e em produção. Não é gambiarra
de desenvolvimento — é a topologia definitiva, e é o que torna `SameSite=Lax` viável sem afrouxar
nada.

Revogação é `session.delete()`. Trocar a senha invalida as demais sessões.

MFA fica preparado (o fluxo de login já é um endpoint próprio) mas não é implementado agora.

## Consequências

- **Bom:** XSS não alcança a sessão; revogação é imediata e sem estrutura extra; o Django já
  entrega hashing, rotação de sessão no login, reset de senha e CSRF prontos — nenhuma
  criptografia caseira.
- **Ruim:** sessão é estado no servidor (Redis/banco) — irrelevante nesta escala. Um cliente
  não-browser (app móvel, integração) precisará de outro mecanismo no futuro; nesse dia, token de
  API por organização, não JWT de usuário.
- **Obrigatório:** o frontend envia `credentials: "include"` e o header CSRF nas requisições que
  alteram estado.

## Alternativas rejeitadas

- **JWT em `localStorage`** — vetado pelo requisito, e com razão: vulnerável a XSS e difícil de revogar.
- **JWT em cookie HTTPOnly** — resolve o XSS, mas mantém o problema da revogação e adiciona
  refresh token, rotação e blacklist, sem vantagem sobre a sessão nesta escala.
- **OAuth/social login** — dependência externa desnecessária para uma ferramenta interna; pode
  ser somado depois sem mudar esta decisão.
