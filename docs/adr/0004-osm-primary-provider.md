# ADR-0004 — OSM/Overpass como provider primário; política de retenção por provider

**Status:** aceito · 2026-08-13

## Contexto

O princípio fundamental do produto é: *"uma empresa é uma entidade permanente no banco"* — com
histórico, várias fontes, diagnósticos e oportunidades ao longo do tempo.

Isso entra em **conflito direto** com os termos do Google Places, a escolha mais óbvia de fonte:

- `place_id` pode ser armazenado indefinidamente
  ([Place IDs](https://developers.google.com/maps/documentation/places/web-service/place-id));
- coordenadas podem ficar em cache por até 30 dias corridos;
- nome, telefone, nota e avaliações **não podem ser pré-buscados, cacheados ou armazenados** —
  precisam ser requisitados ao vivo
  ([Policies](https://developers.google.com/maps/documentation/places/web-service/policies),
  [Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)).

Construir a base do produto em cima disso significaria ou violar contrato, ou não ter banco de
empresas — nenhum dos dois é aceitável.

Alternativas avaliadas para o Brasil:

| Fonte | Armazenável | Custo | Cobertura BR |
|---|---|---|---|
| OpenStreetMap / Overpass | Sim (ODbL, com atribuição) | Grátis | Boa em capitais e cidades médias, irregular no interior |
| Dados Abertos CNPJ (Receita Federal) | Sim (dado público oficial) | Grátis | Total — todo estabelecimento ativo, com CNAE, endereço e telefone |
| Google Places | Não (só `place_id`) | Pago por request | Excelente |

## Decisão

1. **OSM/Overpass é o provider real do MVP.** Grátis, sem chave, dados armazenáveis sob ODbL com
   atribuição, e as tags (`name`, `phone`, `website`, `opening_hours`, endereço) cobrem o que o
   produto precisa para começar.
2. **`Provider.retention_policy`** passa a ser parte do modelo:
   - `PERSIST` — dados podem virar registro permanente (OSM, Receita Federal, Mock);
   - `EPHEMERAL_30D` — só `external_id` é permanente; o resto vive em `CompanySource` com
     `expires_at` e é apagado por task de expurgo.
   Google Places, se um dia entrar, entra como `EPHEMERAL_30D` — e a UI busca esses campos ao vivo.
3. **Cobertura nacional real** vem depois pela ingestão em lote dos Dados Abertos de CNPJ da
   Receita Federal ([repositório oficial](https://www.gov.br/receitafederal/dados)), que também
   fornece o CNPJ — o melhor sinal de deduplicação que existe.
4. **Uso responsável do Overpass público:** ≤1 req/s, backoff exponencial com jitter, User-Agent
   identificando a aplicação, e endpoint configurável por ambiente.

## Consequências

- **Bom:** o banco permanente é legítimo; testes e desenvolvimento não custam nada; o modelo de
  retenção por provider deixa a conformidade explícita no schema em vez de escondida em código.
- **Ruim:** a cobertura inicial é menor que a do Google. Ausência no OSM **não** é ausência no
  mundo — por isso `website_status = NOT_FOUND` e o texto *"Site oficial não identificado nas
  fontes analisadas"* são obrigatórios.
- **Limite conhecido:** o endpoint público do Overpass é comunitário e pode ser retirado a
  qualquer momento ([usage policy](https://operations.osmfoundation.org/policies/api/)). Varrer o
  Brasil inteiro contra ele é abuso — escala exige instância própria ou extratos da Geofabrik.
- **Obrigação:** atribuição "© colaboradores do OpenStreetMap" onde os dados forem exibidos.

## Alternativas rejeitadas

- **Google Places como base** — conflita com o princípio fundamental do produto e custa por request.
- **Scraping de diretórios** — contraria ToS, é frágil, e o requisito proíbe explicitamente.
- **Começar pela ingestão do CNPJ** — ETL pesado de ~5 GB/mês antes de qualquer tela funcionar;
  fica para depois que o motor de busca e a deduplicação estiverem provados.
