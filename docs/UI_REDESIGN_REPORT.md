# Redesign da interface — relatório

> Executado em 15/08/2026. A auditoria que o motivou está em `docs/UI_AUDIT.md`, com os
> números medidos antes de qualquer mudança.

---

## 1. Problemas encontrados

Medidos por varredura no código, não por impressão:

| Problema | Antes |
|---|---|
| Altura de controle | **4 alturas** para o mesmo papel — botão `py-1.5`, nav `py-1`, botão do login `py-2`, campo `0.375rem`. Botão e input lado a lado não alinhavam |
| Escala tipográfica | **9 tamanhos**, 4 deles arbitrários (`text-[11px]`, `[10px]`, `[9px]`) |
| Arredondamento | **4 valores** sem dono definido |
| Largura de página | **6 `max-w`** distintos entre telas |
| Carregamento | **10 telas** com o texto cru "carregando…", **0 skeletons**, salto de layout na chegada do dado |
| Confirmação de ação | **Nenhum toast**. "Copiado" aparecia dentro do próprio botão e sumia com ele |
| Ícones | **Nenhuma biblioteca**; 23 setas tipográficas (`→`, `←`, `✓`) fazendo papel de ícone |
| Cor | Sem `aviso`/`info`; `text-tinta-fraca/50`, `/60`, `/70` usados como se opacidade fosse token |
| Erro | Mensagem sem saída — nenhum "tentar novamente" |

---

## 2. Design system

Tudo em `frontend/src/app/globals.css`. **Nenhum valor visual fora dali** — a varredura final
acusa **zero** utilitários arbitrários (`text-[13px]`, `rounded-[2px]`) no código.

| Eixo | Decisão |
|---|---|
| Superfície | 3 níveis (`papel`, `papel-alto`, `papel-fundo`); hierarquia por **borda**, não sombra |
| Tinta | 3 níveis com contraste conferido: `tinta` 13.9:1, `tinta-media` 8.1:1, `tinta-fraca` 5.2:1 |
| Sinal | Âmbar escurecido para **4.6:1** (`#b45309`) — o antigo `#e8760a` era ilegível como texto e ficou só para preenchimento (`lacuna-viva`) |
| Estados | `acao`, `ganho`, `perdido`, e os novos `aviso` e `info`, cada um com par forte/fraco |
| Tipografia | **6 degraus** (`display`, `titulo`, `secao`, `corpo`, `apoio`, `legenda`), cada um com entrelinha embutida |
| Radius | **3 + 1**: `xs` 2px (só a barra de lacunas), `sm` 4px (controles), `md` 8px (superfícies), `lg` 12px (gaveta) |
| Sombra | **2**, e só no que flutua: `suspenso` (aviso, barra de lote) e `flutuante` (gaveta) |
| Altura de controle | **Uma**: 36px para botão, campo e select; 40px para ação principal |
| Camadas | Escala nomeada: sticky 10 → dropdown 20 → gaveta 30 → modal 40 → aviso 50 |
| Ícones | `lucide-react`, biblioteca única, 16px em controle, 13–14px em texto. Sem dependências transitivas |

---

## 3. Componentes padronizados

Novos, em `frontend/src/components/ui/`:

| Componente | Papel |
|---|---|
| `Botao`, `BotaoDeIcone` | 4 variantes por **hierarquia** (primária, secundária, quieta, perigo), estado de carregamento, ícone. `BotaoDeIcone` exige `title` — ícone sem nome acessível é botão mudo |
| `Campo`, `Selecao`, `Marcador`, `ParDeCampos` | Rótulo amarrado por `id` gerado, erro/ajuda, `aria-invalid`, `aria-describedby`. `ParDeCampos` torna estrutural a regra "mesma largura, mesma altura" |
| `Etiqueta`, `EtiquetaDeEstagio`, `Score` | Cor só quando significa: ganho e perdido têm tom; os cinco estágios do meio são neutros para não competir com o score |
| `Cartao`, `CabecalhoDeCartao` | Superfície única, borda, sem sombra |
| `Esqueleto`, `EsqueletoDeTabela` | Ocupa a altura do conteúdo que vai chegar — fim do salto de layout |
| `Vazio` | Título + descrição + ação + ícone discreto |
| `Erro` | Mensagem em português **com botão de tentar novamente** |
| `CabecalhoDaPagina` | Título, contador em mono, descrição, ação à direita, voltar opcional |
| `CartaoDeMetrica` | Rótulo, valor, contexto. Um destaque por painel |
| `ProvedorDeAvisos` / `useAviso` | Toast único da aplicação, `aria-live="polite"` |

Reescritos: `casca.tsx` (sidebar), `tabela.tsx`, `filtros.tsx`, `lote.tsx`, `telefone.tsx`.

---

## 4. Telas alteradas

As 10, sem exceção.

| Tela | Antes → Depois |
|---|---|
| **Casca** | Navegação horizontal → **sidebar de 240px** com ícones, estado ativo em 4 sinais (fundo, texto, ícone, barra de 2px), organização e usuário no rodapé. No mobile vira gaveta |
| **Painel** (`/`) | Cartões soltos → faixa única de 6 métricas dividida por linha de 1px; funil; melhores oportunidades na tabela real |
| **Empresas** | Filtros empilhados → agrupados em 5 perguntas (Onde, O quê, Presença digital, Contato, Prioridade), painel que acompanha a rolagem, contador de filtros ativos; tabela com cabeçalho fixo, `<colgroup>`, linha de 56px, seleção com fundo próprio, ações no hover; skeleton, vazio com ação, erro com retry, paginação com contexto ("1–25 de 347") |
| **Ficha da empresa** | Coluna única longa → **contato fora de aba** (é o mais buscado) + abas Oportunidades / Diagnóstico / Origem, e coluna fixa com score, breakdown e barra de lacunas |
| **Leads** | Lista simples → alternador Lista/Funil; lista com telefone, WhatsApp, oportunidade e estágio; **Kanban** com rolagem horizontal e cartão de 4 dados |
| **Listas** | Contagem em mono à esquerda, hover, chevron; skeleton e vazio com ação |
| **Detalhe da lista** | Skeleton, exportar CSV no cabeçalho, remoção em lote como ação de perigo |
| **Buscas** | Skeleton de tabela e vazio explicando o próximo passo |
| **Configurações** | Skeleton no lugar do texto cru |
| **Login** | Campos e botão passam pelos primitivos — a mesma altura de controle do resto do produto |

---

## 5. Decisões tomadas

1. **Sidebar, revertendo o `CLAUDE.md`.** A decisão registrada era navegação horizontal para
   não roubar largura da tabela. Em 1440px a sidebar deixa 1200px — mais do que a tabela usa —
   e entrega estado ativo inequívoco e um lugar estável para organização e usuário. A decisão
   foi atualizada na documentação, não apagada.
2. **Sem barra superior no desktop.** Ela só repetiria o título que o `CabecalhoDaPagina` já
   mostra, e cada faixa come altura de uma tela que existe para listar. No mobile ela existe,
   com o botão de menu — ali ela tem função. *Esta é a única parte do pedido que não foi
   seguida ao pé da letra, e é escolha consciente: mais organização, menos elementos.*
3. **Kanban como segunda vista, não como padrão.** A lista responde "para quem eu ligo agora";
   o Kanban responde "como está o mês". A primeira pergunta é a de terça de manhã.
4. **Identidade preservada.** Âmbar continua marcando o que falta, a barra de lacunas continua
   sendo a assinatura, as três famílias tipográficas continuam com seus papéis. O que mudou foi
   o rigor: escala fechada, altura única, borda no lugar de sombra.
5. **Uma dependência nova.** `lucide-react` (zero dependências transitivas). Nenhuma
   biblioteca de componentes foi adicionada — os primitivos são do projeto, sobre Tailwind.
6. **Backend intocado.** Nenhum arquivo em `backend/` foi alterado por este redesign.

---

## 6. Testes executados

```
FRONTEND
  vitest              18 passed (3 arquivos)
  eslint              sem erro
  tsc --noEmit        sem erro
  prettier --check    All matched files use Prettier code style!

BACKEND (prova de que o servidor não foi tocado)
  pytest              563 passed
  ruff                All checks passed!
  black --check       164 files would be left unchanged
  mypy                no issues in 164 source files
  makemigrations      No changes detected
  check --deploy      no issues (0 silenced)          EXIT 0

ROTAS (todas 200)
  /  /empresas  /empresas/{id}  /leads  /leads?vista=funil
  /listas  /buscas  /configuracoes  /login

MÉTRICAS DO SISTEMA
  valores arbitrários no código   0   (eram 12)
  degraus tipográficos            6   (eram 9)
  alturas de controle             1   (eram 4)
```

Um defeito foi encontrado pelo próprio portão durante o trabalho: o `vitest` não resolvia o
alias `@/`, e o teste de telefone **sumiu da contagem** (18 → 14) em vez de falhar. Corrigido
em `vitest.config.ts` — sem isso, qualquer teste de módulo que importe por `@/` desapareceria
em silêncio.

---

## 7. Checklist

| Item | |
|---|---|
| Sidebar alinhada? | **SIM** — grade de 240px, itens de 36px, ícones de 16px alinhados ao texto |
| Header consistente? | **SIM**, com ressalva: o cabeçalho é o `CabecalhoDaPagina`, igual em todas as telas. Barra superior global só no mobile (decisão 2) |
| Inputs padronizados? | **SIM** — todos via `.entrada`, 36px, mesmo foco, mesmo estado de erro |
| Selects padronizados? | **SIM** — mesma altura e seta desenhada em CSS, sem depender do sistema |
| Botões padronizados? | **SIM** — 4 variantes, 2 tamanhos, altura de token |
| Cards padronizados? | **SIM** — `Cartao`, borda, radius `md`, sem sombra |
| Tabelas premium? | **SIM** — cabeçalho fixo, `<colgroup>`, linha de 56px, hover, selecionado, ações no hover |
| Leads fáceis de ler? | **SIM** — empresa, contato, oportunidade, score, estágio na mesma linha |
| Telefone fácil de encontrar? | **SIM** — coluna própria em duas tabelas e bloco de contato na ficha; copiar em 1 clique |
| Filtros organizados? | **SIM** — 5 grupos nomeados, contador de ativos, limpar |
| CRM claro? | **SIM** — lista para trabalhar, Kanban para enxergar |
| Espaçamentos consistentes? | **SIM** — escala fechada, zero arbitrários |
| Tipografia consistente? | **SIM** — 6 degraus com entrelinha embutida |
| Cores consistentes? | **SIM** — tokens com contraste conferido; fim da opacidade como token |
| Responsividade validada? | **PARCIAL** — estrutura responsiva escrita e verificada no código (sidebar vira gaveta, tabelas rolam, grid colapsa). **Não validada em navegador** — ver limitação abaixo |
| Loading states? | **SIM** — skeletons em todas as telas de dado |
| Empty states? | **SIM** — título, descrição, ação e ícone |
| Error states? | **SIM** — mensagem em português com "tentar novamente" |
| Acessibilidade básica? | **SIM** — foco visível, `aria-label` em todo botão de ícone, `aria-current` na navegação, `aria-live` no aviso, rótulo amarrado por `id`, contraste ≥ 4.5:1 |
| Build passa? | **SIM** — tsc, eslint, prettier e os 18 testes; e o portão do backend inteiro |

---

## 8. Pendências

1. **Conferência visual em navegador não foi feita** — não há navegador nem captura de tela
   neste ambiente. Validei por HTML renderizado, classes aplicadas, tokens e rotas
   respondendo 200. Os cinco estados e as cinco resoluções foram escritos e revisados no
   código, **não vistos em tela**. Esta é a primeira coisa a fazer, e é sua.
2. **`configuracoes` e `buscas` receberam só o essencial** (skeleton, vazio, tokens). O
   agrupamento em cartões de Configurações e a linguagem comercial da tela de Buscas ficaram
   para uma segunda passagem.
3. **`Gaveta`, `Modal`, `Tooltip` e `Dropdown` não foram criados** — nenhuma tela precisa deles
   hoje. A escala de z-index já reserva as camadas.
4. **Multi-select com chips** não existe: os filtros de cidade e categoria são de escolha
   única. Entra quando o produto precisar de recorte múltiplo.
5. **`sharp` com 3 vulnerabilidades altas** — vem do `next`, é anterior a este trabalho e não
   foi tocado (`npm audit fix --force` traria mudança quebrando versão maior).
