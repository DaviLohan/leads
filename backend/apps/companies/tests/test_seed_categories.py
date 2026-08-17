"""O catálogo de ramos de atuação.

Vale testar porque é dado de produto disfarçado de fixture: até aqui ele morava dentro do
`seed_dev_data`, que recusa rodar sem `DEBUG=True`, e o efeito era não existir categoria
nenhuma em produção — logo, nenhuma busca possível.
"""

import pytest
from django.core.management import call_command

from apps.companies.management.commands.seed_categories import CATEGORIAS, OSM
from apps.companies.models import Category

pytestmark = pytest.mark.django_db


class TestCatalogo:
    def test_cria_o_catalogo_inteiro(self):
        call_command("seed_categories")

        assert Category.objects.count() == len(CATEGORIAS)

    def test_reexecutar_nao_duplica(self):
        call_command("seed_categories")
        call_command("seed_categories")

        assert Category.objects.count() == len(CATEGORIAS)

    def test_slugs_sao_unicos_na_constante(self):
        """Slug repetido não daria erro: a segunda linha sobrescreveria a primeira em
        silêncio, e o catálogo sairia menor do que a lista sem ninguém notar."""
        slugs = [slug for slug, _, _ in CATEGORIAS]

        assert len(slugs) == len(set(slugs))

    def test_toda_categoria_sabe_traduzir_para_o_osm(self):
        """Categoria sem mapeamento não gera job (`discovery.services.plan_search`), então
        entraria no menu e produziria uma busca vazia."""
        call_command("seed_categories")

        for categoria in Category.objects.all():
            tag = categoria.provider_mapping.get(OSM)
            assert tag, f"{categoria.slug} não traduz para {OSM}"
            assert (
                len(tag) == 1
            ), f"{categoria.slug} tem {len(tag)} tags; várias viram AND no Overpass QL"

    def test_nenhuma_tag_repetida_entre_categorias(self):
        """Duas categorias com a mesma tag são duas linhas de menu que devolvem exatamente a
        mesma lista — o usuário escolhe uma, desconfia, escolhe a outra e vê o mesmo.

        Foi o que impediu "Concessionárias" de virar categoria própria: no OSM `shop=car` é a
        tag de venda de carro, sem separar concessionária de revenda de usado.
        """
        tags = [tuple(sorted(tag.items())) for _, _, tag in CATEGORIAS]

        assert len(tags) == len(set(tags))


class TestAtualizacao:
    def test_corrige_tag_errada_em_banco_ja_semeado(self):
        """O seed anterior usava `get_or_create` com `defaults`: corrigir uma tag na
        constante não propagava, e o banco ficava com o valor errado para sempre."""
        Category.objects.create(
            slug="roupas", name="Nome antigo", provider_mapping={OSM: {"shop": "errado"}}
        )

        call_command("seed_categories")

        roupas = Category.objects.get(slug="roupas")
        assert roupas.name == "Lojas de roupas"
        assert roupas.provider_mapping == {OSM: {"shop": "clothes"}}

    def test_nao_reativa_ramo_desligado_no_admin(self):
        """`is_active` fica fora do `defaults` de propósito: reimportar o catálogo não pode
        devolver ao menu um ramo que alguém tirou de lá."""
        call_command("seed_categories")
        Category.objects.filter(slug="bares").update(is_active=False)

        call_command("seed_categories")

        assert Category.objects.get(slug="bares").is_active is False

    def test_nao_apaga_categoria_fora_do_catalogo(self):
        """Categoria criada à mão no admin sobrevive ao seed."""
        Category.objects.create(slug="cartorios", name="Cartórios")

        call_command("seed_categories")

        assert Category.objects.filter(slug="cartorios").exists()


def test_seed_dev_data_continua_preparando_o_catalogo(settings):
    """`make seed` precisa continuar entregando uma base utilizável."""
    settings.DEBUG = True

    call_command("seed_dev_data")

    assert Category.objects.count() == len(CATEGORIAS)
