import pytest

from apps.core.text import normalize_name


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("São Paulo", "sao paulo"),
        ("SÃO PAULO", "sao paulo"),
        ("  Sao   Paulo  ", "sao paulo"),
        ("Açaí", "acai"),
        ("Ji-Paraná", "ji-parana"),
        ("Olho d'Água", "olho d'agua"),
        ("Município", "municipio"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normaliza_acento_caixa_e_espaco(entrada, esperado):
    assert normalize_name(entrada) == esperado


def test_formas_diferentes_da_mesma_cidade_convergem():
    """É esta propriedade que faz a busca funcionar — as variações têm de colidir."""
    variacoes = ["São Paulo", "sao paulo", "SAO  PAULO", "São  paulo "]
    assert len({normalize_name(v) for v in variacoes}) == 1


def test_hifen_e_apostrofo_sobrevivem():
    """Só acento, caixa e espaço são normalizados: o resto do nome é preservado."""
    assert normalize_name("Santa Bárbara d'Oeste") == "santa barbara d'oeste"
