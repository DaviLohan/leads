# ADR-0007 — Fronteira de multi-tenancy: dado público global, dado comercial por organização

**Status:** aceito · 2026-08-13

## Contexto

O requisito pede preparo para múltiplas organizações, sem vazamento entre elas, e diz que dados
públicos de empresas "podem futuramente ser compartilhados de maneira controlada".

Isso força uma escolha que define o schema inteiro. Se `Company` pertencesse à organização, cada
tenant redescobriria e reanalisaria as mesmas empresas — multiplicando chamadas de API, varreduras
de site e linhas no banco, para gerar exatamente o mesmo resultado. Se tudo fosse global,
anotações e negociações vazariam entre concorrentes.

## Decisão

Fronteira explícita, marcada em cada tabela do ERD:

**Global (🌐)** — o que descreve a empresa no mundo real, verificável por qualquer um:
`Company`, `CompanyAddress`, `CompanyContact`, `CompanyWebsite`, `CompanySocialProfile`,
`CompanySource`, `Category`, `State`, `City`, `WebsiteScan`, `WebsiteFinding`, `Opportunity`,
`Score`, `Provider`.

**Da Organization (🔒)** — o que é interpretação, esforço ou relacionamento comercial:
`Lead`, `Interaction`, `Note`, `Task`, `SuppressionEntry`, `Search`, `SearchJob`, `SearchResult`,
`ProviderCredential`, `ProviderUsage`, configurações e pesos customizados.

Regra de leitura: *"outra empresa poderia descobrir isso sozinha na internet?"* Se sim, é global.
Se depende do trabalho ou da opinião de um cliente nosso, é do tenant.

Aplicação:

- Todo model de tenant tem `organization` não-nulo e usa manager que exige o escopo.
- O tenant vem do request (membership do usuário), nunca de parâmetro enviado pelo cliente.
- Existe teste de isolamento cobrindo cada model de tenant. Ele não pode ser removido.
- `Score` e `Opportunity` são globais porque derivam só de dado público. Pesos customizados por
  organização, quando existirem, geram score próprio marcado com a versão da regra.

## Consequências

- **Bom:** descoberta e análise são pagas uma vez e aproveitadas por todos os tenants — que é o
  que torna o modelo SaaS viável. Custo de API não cresce linearmente com o número de clientes.
- **Ruim:** a fronteira precisa ser respeitada com disciplina; um campo comercial colocado por
  engano em `Company` vira vazamento entre organizações. Daí a marcação no ERD e os testes.
- **Efeito colateral aceito:** correção de dado público feita por um tenant beneficia os outros.
  Auditoria registra quem alterou.

## Alternativas rejeitadas

- **Isolamento total (tudo por organização)** — duplica dado e custo de API sem benefício real;
  inviabiliza o compartilhamento controlado previsto no requisito.
- **Um schema Postgres por tenant** — complica migrations e consultas analíticas cruzadas, e
  resolve um problema de isolamento que a coluna `organization` já resolve nesta escala.
- **Row-Level Security no Postgres** — defesa em profundidade legítima, mas exige gestão de role
  por conexão que não combina com pool de conexões. Pode ser somado depois sem mudar o schema.
