"""Catálogo de ramos de atuação, com a tradução para as tags de cada fonte.

Isto **não** é dado de desenvolvimento, e por isso não tem guarda de `DEBUG`: é o catálogo
do produto, como `seed_opportunity_types` e `seed_pipeline`. Antes ele morava dentro do
`seed_dev_data`, que recusa rodar sem `DEBUG=True` — o efeito era não existir categoria
nenhuma em produção, e portanto nenhuma busca possível.

`provider_mapping` é o que evita categoria hardcoded dentro do provider (ADR-0003). O
formato é `{slug_da_fonte: {chave_osm: valor_osm}}`, e várias chaves viram **AND** no
Overpass QL (`providers/overpass.py:build_query`) — por isso cada categoria tem exatamente
uma tag. Categoria sem chave para uma fonte simplesmente não gera job nela.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

OSM = "osm-overpass"

# (slug, nome, tag OSM). O slug é a chave de idempotência e o que o filtro da API aceita
# (`?category=roupas,calcados`); mudá-lo depois quebra link e filtro salvo pelo usuário.
#
# Duas tags ficaram de fora de propósito: `amenity=school`, porque no OSM brasileiro o dado
# é dominado por escola pública e viraria ruído numa lista de prospecção, e
# `amenity=doctors`, que sobrepõe `amenity=clinic` sem acrescentar recorte.
CATEGORIAS: list[tuple[str, str, dict[str, str]]] = [
    # Saúde
    ("dentistas", "Dentistas", {"amenity": "dentist"}),
    ("veterinarias", "Veterinárias", {"amenity": "veterinary"}),
    ("farmacias", "Farmácias", {"amenity": "pharmacy"}),
    ("clinicas", "Clínicas", {"amenity": "clinic"}),
    ("laboratorios", "Laboratórios", {"healthcare": "laboratory"}),
    ("psicologos", "Psicólogos", {"healthcare": "psychotherapist"}),
    ("fisioterapia", "Fisioterapia", {"healthcare": "physiotherapist"}),
    # Vestuário
    ("roupas", "Lojas de roupas", {"shop": "clothes"}),
    ("calcados", "Calçados", {"shop": "shoes"}),
    ("joalherias", "Joalherias", {"shop": "jewelry"}),
    # Automotivo
    # O nome cobre os dois porque o OSM não os separa: `shop=car` é a tag de venda de carro,
    # concessionária de marca ou revenda de usado. A distinção existiria em `second_hand`,
    # que quase ninguém preenche no Brasil — medido em 17/08/2026, Cascavel tinha 7 lojas e
    # zero com a tag. Categoria filtrando por ela voltaria vazia; duas categorias sobre a
    # mesma tag seriam duas linhas de menu com resultado idêntico.
    ("carros", "Concessionárias e revendas de carros", {"shop": "car"}),
    ("locadoras", "Locadoras de carros", {"amenity": "car_rental"}),
    ("autopecas", "Autopeças", {"shop": "car_parts"}),
    ("oficinas", "Oficinas mecânicas", {"shop": "car_repair"}),
    ("motos", "Motos", {"shop": "motorcycle"}),
    ("lava-rapido", "Lava-rápido", {"amenity": "car_wash"}),
    ("postos", "Postos de combustível", {"amenity": "fuel"}),
    # Casa e construção
    ("construcao", "Material de construção", {"shop": "doityourself"}),
    ("moveis", "Móveis", {"shop": "furniture"}),
    ("eletronicos", "Eletrônicos", {"shop": "electronics"}),
    # Varejo alimentar
    ("supermercados", "Supermercados", {"shop": "supermarket"}),
    ("mercearias", "Mercearias", {"shop": "convenience"}),
    ("acougues", "Açougues", {"shop": "butcher"}),
    ("hortifrutis", "Hortifrútis", {"shop": "greengrocer"}),
    ("padarias", "Padarias", {"shop": "bakery"}),
    # Alimentação
    ("restaurantes", "Restaurantes", {"amenity": "restaurant"}),
    ("lanchonetes", "Lanchonetes", {"amenity": "fast_food"}),
    ("bares", "Bares", {"amenity": "bar"}),
    ("cafeterias", "Cafeterias", {"amenity": "cafe"}),
    ("sorveterias", "Sorveterias", {"amenity": "ice_cream"}),
    # Serviços e comércio de rua
    ("lavanderias", "Lavanderias", {"shop": "laundry"}),
    ("petshops", "Petshops", {"shop": "pet"}),
    ("oticas", "Óticas", {"shop": "optician"}),
    ("papelarias", "Papelarias", {"shop": "stationery"}),
    ("floriculturas", "Floriculturas", {"shop": "florist"}),
    ("livrarias", "Livrarias", {"shop": "books"}),
    ("celulares", "Celulares e assistência", {"shop": "mobile_phone"}),
    # Beleza e bem-estar
    ("saloes", "Salões de beleza", {"shop": "hairdresser"}),
    ("estetica", "Clínicas de estética", {"shop": "beauty"}),
    ("academias", "Academias", {"leisure": "fitness_centre"}),
    # Escritórios
    ("imobiliarias", "Imobiliárias", {"office": "estate_agent"}),
    ("contabilidade", "Contabilidade", {"office": "accountant"}),
    ("advocacia", "Advocacia", {"office": "lawyer"}),
    ("seguros", "Corretoras de seguros", {"office": "insurance"}),
    # Educação
    ("autoescolas", "Autoescolas", {"amenity": "driving_school"}),
    ("idiomas", "Cursos de idiomas", {"amenity": "language_school"}),
    ("creches", "Creches", {"amenity": "kindergarten"}),
    # Hotelaria
    ("hoteis", "Hotéis", {"tourism": "hotel"}),
    ("pousadas", "Pousadas", {"tourism": "guest_house"}),
]


class Command(BaseCommand):
    help = "Cria ou atualiza o catálogo de ramos de atuação."

    def handle(self, *args, **options) -> None:
        from apps.companies.models import Category

        criadas = 0
        for slug, nome, tag in CATEGORIAS:
            # `update_or_create` (e não `get_or_create`) para que corrigir uma tag errada
            # aqui propague para banco já semeado — a mesma semântica de `import_ibge`.
            # `is_active` fica **fora** do `defaults` de propósito: reimportar o catálogo não
            # pode reativar um ramo que alguém desligou no admin.
            _, novo = Category.objects.update_or_create(
                slug=slug,
                defaults={"name": nome, "provider_mapping": {OSM: tag}},
            )
            criadas += novo

        self.stdout.write(
            self.style.SUCCESS(
                f"Categorias: {criadas} criada(s), "
                f"{len(CATEGORIAS) - criadas} atualizada(s). "
                f"Total no catálogo: {Category.objects.count()}."
            )
        )
