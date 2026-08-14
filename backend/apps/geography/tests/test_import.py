import copy

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import IntegrityError

from apps.geography.models import City, State
from apps.geography.services import GeographyImportError, import_cities, import_states

pytestmark = pytest.mark.django_db


def test_importa_estados_e_municipios(estados, municipios):
    resultado_uf = import_states(estados)
    resultado_cidades = import_cities(municipios)

    assert (resultado_uf.created, resultado_uf.updated) == (2, 0)
    assert (resultado_cidades.created, resultado_cidades.updated) == (3, 0)

    parana = State.objects.get(uf="PR")
    assert parana.ibge_code == "41"
    assert parana.region == "S"
    assert parana.cities.count() == 2


def test_municipio_sem_microrregiao_resolve_pela_regiao_imediata(estados, municipios):
    """Municípios criados depois de 2017 não têm `microrregiao` — não podem sumir."""
    import_states(estados)
    import_cities(municipios)

    sao_paulo = City.objects.get(ibge_code="3550308")
    assert sao_paulo.state.uf == "SP"


def test_reimportar_atualiza_e_nao_duplica(estados, municipios):
    import_states(estados)
    import_cities(municipios)

    resultado_uf = import_states(estados)
    resultado_cidades = import_cities(municipios)

    assert (resultado_uf.created, resultado_uf.updated) == (0, 2)
    assert (resultado_cidades.created, resultado_cidades.updated) == (0, 3)
    assert State.objects.count() == 2
    assert City.objects.count() == 3


def test_renomear_municipio_atualiza_o_nome_normalizado(estados, municipios):
    """O `update_or_create` grava com `update_fields`; o campo derivado tem de ir junto.

    Sem isso o município renomeado continuaria encontrável só pelo nome antigo.
    """
    import_states(estados)
    import_cities(municipios)

    renomeado = copy.deepcopy(municipios)
    renomeado[0]["nome"] = "Londrina do Norte"
    import_cities(renomeado)

    londrina = City.objects.get(ibge_code="4113700")
    assert londrina.name == "Londrina do Norte"
    assert londrina.normalized_name == "londrina do norte"


def test_nome_normalizado_sai_do_nome(estados, municipios):
    import_states(estados)
    import_cities(municipios)

    assert City.objects.get(ibge_code="3550308").normalized_name == "sao paulo"


def test_municipio_sem_estado_na_base_aborta_tudo(estados, municipios):
    """Payload truncado precisa quebrar, não deixar um estado sem cidades em silêncio."""
    import_states([estados[0]])  # só o Paraná

    with pytest.raises(GeographyImportError, match="São Paulo"):
        import_cities(municipios)

    # A transação do serviço desfez as duas cidades do Paraná que já haviam entrado.
    assert City.objects.count() == 0


def test_regiao_desconhecida_aborta(estados):
    quebrado = copy.deepcopy(estados)
    quebrado[0]["regiao"]["sigla"] = "XX"

    with pytest.raises(GeographyImportError, match="Região desconhecida"):
        import_states(quebrado)

    assert State.objects.count() == 0


def test_banco_recusa_codigo_ibge_fora_do_formato(estados):
    import_states(estados)
    parana = State.objects.get(uf="PR")

    with pytest.raises(IntegrityError):
        City.objects.create(ibge_code="41137", name="Curta", state=parana)


def test_comando_importa_de_arquivo(tmp_path, estados, municipios):
    import json

    arquivo = tmp_path / "ibge.json"
    arquivo.write_text(json.dumps({"estados": estados, "municipios": municipios}), encoding="utf-8")

    call_command("import_ibge", "--file", str(arquivo))

    assert State.objects.count() == 2
    assert City.objects.count() == 3


def test_comando_recusa_arquivo_sem_as_chaves(tmp_path):
    arquivo = tmp_path / "ruim.json"
    arquivo.write_text('{"estados": []}', encoding="utf-8")

    with pytest.raises(CommandError, match="estados"):
        call_command("import_ibge", "--file", str(arquivo))
