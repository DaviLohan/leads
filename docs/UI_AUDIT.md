# Auditoria visual da interface

> Levantamento feito antes do redesign, em 15/08/2026, sobre as 10 telas e 6 componentes que
> existiam. Tudo aqui é medido por varredura no código — nenhum número é impressão.
>
> Método: `grep` sobre `frontend/src/app` e `frontend/src/components`, contando valores
> distintos de cada propriedade visual. Onde o mesmo papel na interface tem mais de um valor,
> é inconsistência.

---

## 1. Inventário

**Telas (10):** `login`, `/` (painel), `empresas`, `empresas/[id]`, `leads`, `leads/[id]`,
`listas`, `listas/[id]`, `buscas`, `configuracoes`.

**Componentes (6):** `casca` (navegação + `Cabecalho`, `Botao`, `Etiqueta`, `Vazio`, `Erro`),
`tabela`, `filtros`, `lote`, `telefone`, `lacunas` (`BarraDeLacunas`, `Score`).

**O que não existia:** sidebar, tabs, drawer, modal, tooltip, dropdown, toast, skeleton,
paginação padronizada, biblioteca de ícones, cartão de métrica.

---

## 2. Inconsistências medidas

### 2.1 Altura de controle — a mais visível

Quatro alturas diferentes para coisas que deveriam medir igual:

| Elemento | Onde | Padding vertical |
|---|---|---|
| Botão | `casca.tsx:169` | `py-1.5` |
| Link de navegação | `casca.tsx:70` | `py-1` |
| Botão do login | `login/page.tsx:79` | `py-2` |
| Input do login | `login/page.tsx:54,66` | `py-2` |
| Campo de filtro (`.entrada`) | `globals.css` | `0.375rem` |

Efeito: um botão ao lado de um input, na mesma linha, não alinha. É o que faz a barra de
filtros parecer montada às pressas.

### 2.2 Tipografia — 9 tamanhos, 4 deles arbitrários

```
74× text-sm     61× text-xs      6× text-[11px]    3× text-[10px]
 3× text-3xl     3× text-2xl     2× text-lg        1× text-xl      1× text-[9px]
```

Três tamanhos arbitrários em pixel (`[11px]`, `[10px]`, `[9px]`) para o mesmo papel — rótulo
secundário — em telas diferentes. E dois degraus de título (`2xl`, `3xl`) sem regra de quando
usar cada um.

### 2.3 Arredondamento — 4 valores

```
21× rounded (4px)   16× rounded-lg (6px)   4× rounded-full   2× rounded-[2px]
```

`rounded` e `rounded-lg` aparecem no mesmo tipo de elemento em telas diferentes.

### 2.4 Largura de página — 6 valores

`max-w-6xl` na casca, e `2xl`, `xl`, `md`, `sm` espalhados nas telas. Cada página termina numa
coluna de largura diferente, o que quebra a sensação de ser o mesmo produto.

### 2.5 Valores arbitrários

12 ocorrências de `[...]`: `w-[62rem]`, `min-w-[58rem]`, `h-[3px]`, `text-[9px]`,
`tracking-[0.08em]`, `rounded-[2px]`. Larguras de tabela chutadas em `rem` diferentes entre a
tabela de empresas e a de leads.

### 2.6 Espaçamento

Vinte e dois valores distintos entre `px`, `py`, `gap`, `mt`, `mb` e `space-y`. Os mais usados
(`px-3`, `py-3`, `gap-3`) convivem com `px-2.5`, `py-1.5`, `gap-1`, `p-5` sem critério.

### 2.7 Estados

| Estado | Situação |
|---|---|
| Carregando | **10 telas** com o texto cru "carregando…". Zero skeletons. Layout salta quando o dado chega |
| Vazio | Existe e é bom (`Vazio` em 8 telas, sempre com ação) |
| Erro | Existe (`Erro` em 9 telas), mas sem botão "tentar de novo" |
| Confirmação | **Não existe toast.** Copiar telefone dá um "copiado" que some no próprio botão; salvar em lista escreve texto solto na barra |

### 2.8 Ícones

**Nenhuma biblioteca instalada.** 23 ocorrências de setas e sinais tipográficos fazendo papel
de ícone: `→` para "abrir", `←` para voltar, `·` como separador, `✓` para confirmado. Não
alinham verticalmente com o texto, não escalam e não têm peso consistente.

### 2.9 Cor

13 tokens definidos, bem nomeados e com tese clara (âmbar = lacuna). Faltam: `aviso`, `info`,
um terceiro nível de tinta para texto realmente secundário, e uma definição de quando usar
borda × superfície × sombra. Há `text-tinta-fraca/60`, `/50` e `/70` espalhados — opacidade
usada como se fosse token de cor.

---

## 3. O que está certo e não deve ser mexido

- **A tese**: âmbar marca o que **falta**, cinza o que existe. É o inverso de toda barra de
  progresso e é o que faz uma lista de trinta empresas ser lida num segundo.
- **`BarraDeLacunas`**: cinco segmentos, hachura para "não verificado". Elemento assinatura.
- **Três famílias tipográficas** com papéis distintos: Chivo (título), Archivo (corpo),
  Azeret Mono (todo número). Números tabulares alinhados em coluna é o que permite varrer uma
  lista de ligações com o olho.
- **Fundo papel de escritório** (cinza-verde frio), não creme.
- **Nomes em português** em telas, rotas e componentes.
- **`Vazio` nunca é só "nada aqui"** — sempre diz o próximo passo.

---

## 4. Prioridade de correção

1. Altura de controle unificada (o desalinhamento mais visível).
2. Escala tipográfica e de espaçamento fechadas em tokens.
3. Casca: sidebar + header + container único.
4. Tabela premium (é o produto).
5. Estados: skeleton, erro com retry, toast.
6. Ícones de biblioteca única.
7. Cor: `aviso`/`info` e fim da opacidade-como-token.
