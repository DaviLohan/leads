# Segurança

Este documento descreve as decisões de segurança do projeto e o que é obrigatório manter.
Nenhum item aqui pode ser desativado para "resolver" um bug.

## Modelo de ameaças (resumo)

| Ativo | Ameaça principal | Mitigação |
|---|---|---|
| Dados comerciais de uma organização | Vazamento entre tenants | Fronteira de tenancy explícita + manager com escopo + teste de isolamento obrigatório |
| Rede interna / metadata de cloud | SSRF pelo analisador de sites | Guard de SSRF com validação de IP pós-DNS e por redirect |
| Contas de usuário | Roubo de sessão, força bruta | Cookie HTTPOnly/Secure/SameSite, CSRF, throttling em login e reset |
| Credenciais de providers | Exposição em log ou repositório | Somente variáveis de ambiente; filtro de log; nunca no Git |
| Integridade dos dados | Merge destrutivo, corrida entre workers | Transações, constraints no banco, locks distribuídos, auditoria |
| Reputação / conformidade | Contato indevido, LGPD | Lista de supressão aplicada na ingestão, registro de fonte e data de cada dado |

## SSRF — a parte mais crítica

O analisador de sites recebe URLs vindas de fontes externas e de usuários. Validar a string
antes de conectar **não basta**: o DNS pode mudar entre a validação e a conexão (TOCTOU) e
cada redirect é uma nova chance de escapar.

Obrigatório:

1. Apenas esquemas `http` e `https`. Nada de `file:`, `gopher:`, `ftp:`, `data:`.
2. Resolver o hostname manualmente e validar **todos** os IPs retornados (A e AAAA).
3. Bloquear: `127.0.0.0/8`, `::1`, `0.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`,
   `169.254/16` (inclui `169.254.169.254` — metadata de cloud), `fc00::/7`, `fe80::/10`,
   multicast, reservados, e IPv4 mapeado em IPv6.
4. Conectar no **IP já validado**, enviando o `Host` original — não deixar a lib resolver de novo.
5. Revalidar a cada redirect. Máximo de 3 redirects.
6. Timeout de conexão e de leitura, e teto de bytes lidos (streaming com corte).
7. Sem redirect para esquema diferente de http/https.

Testes de SSRF são pré-requisito para o scanner existir — o código de scan não vai para a
branch principal sem eles.

## Autenticação (ADR-0005)

- Sessão Django em cookie: `HttpOnly`, `SameSite=Lax`, `Secure` em produção.
- Sem JWT e sem token em `localStorage` — XSS não deve conseguir roubar a sessão.
- O frontend Next.js faz rewrite de `/api/*` para o backend, então o browser trata tudo como
  mesma origem. Isso é o que torna `SameSite=Lax` viável sem afrouxar nada.
- Senhas com o hasher do Django (PBKDF2/Argon2). Nunca algoritmo próprio, nunca reversível.
- Logout e revogação = apagar a sessão no servidor.
- MFA previsto, não implementado ainda.

## Autorização

RBAC com papéis `OWNER`, `ADMIN`, `MANAGER`, `SALES`, `VIEWER`. Verificação **sempre** no
backend, por objeto quando aplicável. O frontend só esconde o que o backend já nega.

## CSRF

Proteção do Django ativa. Requisições que alteram estado exigem o token. Como a autenticação
usa cookie, desabilitar CSRF é equivalente a abrir a aplicação — nunca é a solução certa.

## Headers e CORS

Configurados em produção: HSTS (com preload), `X-Content-Type-Options: nosniff`,
`Referrer-Policy: same-origin`, `X-Frame-Options: DENY`, CSP restritiva, cookies `Secure`,
redirect para HTTPS. CORS restrito à lista de origens do ambiente — `*` nunca em produção.

## Rate limiting

- **Da nossa API**: throttling do DRF em login, recuperação de senha, criação de busca e
  endpoints caros de análise.
- **Para fora**: nenhuma chamada a provider externo sem passar pelo limitador em Redis, com
  backoff exponencial + jitter, número máximo de tentativas e timeout. Sem retry infinito.

## Segredos

- Só via variável de ambiente ou secret manager. `.env.example` é versionado; `.env` não.
- `SECRET_KEY` em produção é obrigatória e a aplicação falha na inicialização se estiver
  ausente ou for o valor de desenvolvimento.
- Verificação de segredos no `pre-commit` e no CI.
- Se um segredo vazar para o histórico do Git: rotacionar primeiro, limpar o histórico depois.

## Logs

Nunca registrar senha, token, cookie, `Authorization`, secret ou API key. O filtro de logging
mascara esses campos por nome. `request_id` correlaciona a requisição HTTP com as tasks Celery
que ela originou.

## Injeção

SQL sempre via ORM ou query parametrizada — concatenação de string com entrada do usuário é
proibida. No frontend, nada de `dangerouslySetInnerHTML` com conteúdo não sanitizado; React
escapa por padrão e é assim que deve ficar.

## Uploads

Ainda não existem. Quando existirem: validar MIME real (não a extensão), limitar tamanho,
renomear o arquivo, nunca confiar no nome enviado, armazenar fora de diretório executável e
servir por object storage.

## LGPD e uso legítimo de dados

A plataforma é B2B e trabalha com informações comerciais legitimamente públicas.

**Não é desenvolvido** — e não será aceito em PR — nada que sirva para: descobrir telefone ou
e-mail pessoal oculto, quebrar mecanismo de privacidade, contornar autenticação, burlar CAPTCHA,
contornar bloqueio técnico, violar Terms of Service ou acessar sistema sem autorização.

Cada dado relevante guarda **fonte, data de coleta, tipo, última verificação, status e
confiabilidade**. Substituir informação sem manter rastreabilidade é proibido.

Ponto de atenção real: MEI e profissional liberal são pessoa física, e o telefone "comercial"
pode ser pessoal. Por isso:

- Base legal para prospecção é o legítimo interesse, com **opt-out obrigatório e registrado**.
- `SuppressionEntry` é indexada por identificador normalizado (telefone E.164, e-mail, domínio,
  CNPJ) — e não apenas pelo ID da empresa, que muda quando ela é redescoberta por outra fonte.
- A supressão é verificada **no pipeline de ingestão**, antes de persistir e antes de enfileirar
  qualquer contato. Empresa marcada como `DO_NOT_CONTACT` some das filas automáticas e exibe o
  status com destaque.
- Existe caminho para exclusão, bloqueio e supressão de registros a pedido do titular.

## Termos de terceiros

Cada provider declara sua política de retenção (ADR-0004). Google Places, por exemplo, permite
armazenar `place_id` indefinidamente mas **não** nome, telefone, nota ou avaliações — por isso
não é a base do produto. Provider marcado como efêmero só persiste o identificador externo e um
cache com expiração, com task de expurgo. Violar isso é violar contrato, não é detalhe técnico.

## Auditoria

`AuditLog` é append-only: sem update, sem delete pela aplicação. Registra alteração de usuário,
de permissão, exclusão, merge de empresa, mudança de configuração e de provider. Usuário comum
não consegue alterá-lo.

## Dependências

`pip-audit` e `npm audit` no CI, Dependabot ativo. Antes de adicionar biblioteca: é mesmo
necessária? é madura? é mantida? a licença serve? Preferir o que é amplamente usado; evitar
pacote obscuro.

## Reportar vulnerabilidade

Uso interno no momento. Contato: o responsável técnico do repositório. Não abrir issue pública
com detalhe explorável.
