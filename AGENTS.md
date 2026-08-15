# Para agentes de IA

Leia, nesta ordem, antes de mudar qualquer coisa:

1. **`CLAUDE.md`** (raiz) — as regras: o que é obrigatório, o que é proibido, e as decisões
   travadas. Regra daqui vence preferência pessoal e vence este arquivo.
2. **`docs/BRIEFING.md`** — o mapa: o que o produto faz, os oito apps, o modelo de dados, a
   superfície da API, as telas, as armadilhas do ambiente, e a tabela "onde mexer para cada
   tipo de mudança".
3. O ADR relacionado ao que você vai tocar, em `docs/adr/`.

Resumo em três linhas, para o caso de você só ler isto:

- Plataforma B2B brasileira que encontra empresas com **lacunas digitais** e as transforma em
  leads. Monólito modular Django + Next.js, PostgreSQL/PostGIS, Celery.
- A regra que sustenta o produto: **"não sei" nunca vira "não tem"**. Nunca afirme que uma
  empresa não tem site — o correto é "Site oficial não identificado nas fontes analisadas".
- Dado público é global; dado comercial pertence à `Organization`. Recurso de outra
  organização responde **404**, nunca 403.

Antes de encerrar qualquer tarefa: `make test` e `make lint` — **e os quatro portões da CI que
eles não cobrem** (`docs/BRIEFING.md` §2, entre eles a checagem de deploy com settings de
produção, que já quebrou passando no lint local). Reporte a saída real, nunca "deve funcionar".
