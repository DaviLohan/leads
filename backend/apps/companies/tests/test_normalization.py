import pytest

from apps.companies.normalization import (
    normalize_domain,
    normalize_phone,
    normalize_tax_id,
    normalize_url,
)


class TestCNPJ:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("11.222.333/0001-81", "11222333000181"),
            ("11222333000181", "11222333000181"),
            ("  11 222 333 0001 81  ", "11222333000181"),
            ("CNPJ: 11.222.333/0001-81", "11222333000181"),
        ],
    )
    def test_aceita_com_e_sem_mascara(self, entrada, esperado):
        assert normalize_tax_id(entrada) == esperado

    def test_recusa_digito_verificador_errado(self):
        """CNPJ é sinal forte de dedup — um dígito trocado fundiria empresas distintas."""
        assert normalize_tax_id("11222333000182") is None

    @pytest.mark.parametrize(
        "invalido",
        [
            "1122233300018",  # 13 dígitos
            "112223330001812",  # 15 dígitos
            "00000000000000",  # repetido: passa no módulo 11 por acidente
            "11111111111111",
            "abcdefghijklmn",
            "",
            None,
        ],
    )
    def test_recusa_entrada_invalida(self, invalido):
        assert normalize_tax_id(invalido) is None

    def test_nunca_devolve_o_valor_cru(self):
        """Valor meio normalizado no banco quebraria a unicidade em silêncio."""
        for entrada in ["11222333000182", "123", "lixo"]:
            assert normalize_tax_id(entrada) is None


class TestTelefone:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("(43) 99999-8888", "+5543999998888"),
            ("43999998888", "+5543999998888"),
            ("+55 43 99999-8888", "+5543999998888"),
            ("+5543999998888", "+5543999998888"),
            ("43 3324-1000", "+554333241000"),  # fixo, 8 dígitos
            ("(11) 3333-4444", "+551133334444"),
        ],
    )
    def test_converte_para_e164(self, entrada, esperado):
        assert normalize_phone(entrada) == esperado

    def test_celular_sem_o_nono_digito_e_recusado(self):
        """Erro clássico de base velha: celular gravado com 8 dígitos, antes do nono.

        `43 99999-8888` é válido; `43 9999-8888` não — fixo brasileiro não começa com 9.
        Aceitar o segundo criaria um E.164 que não existe e nunca casaria na supressão.
        """
        assert normalize_phone("43 99999-8888") == "+5543999998888"
        assert normalize_phone("43 9999-8888") is None

    def test_formas_diferentes_do_mesmo_numero_convergem(self):
        """É disso que a supressão da LGPD depende: sem forma única, o opt-out vaza."""
        variacoes = ["(43) 99999-8888", "43 99999 8888", "+55 (43) 99999-8888", "043999998888"]
        assert len({normalize_phone(v) for v in variacoes}) == 1

    @pytest.mark.parametrize("invalido", ["", None, "abc", "1", "999", "(00) 0000-0000"])
    def test_recusa_entrada_invalida(self, invalido):
        assert normalize_phone(invalido) is None

    def test_numero_estrangeiro_com_codigo_de_pais(self):
        assert normalize_phone("+1 202 555 0143") == "+12025550143"


class TestDominio:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("https://www.exemplo.com.br/contato", "exemplo.com.br"),
            ("HTTPS://WWW.Exemplo.COM.BR", "exemplo.com.br"),
            ("http://exemplo.com.br", "exemplo.com.br"),
            ("exemplo.com.br", "exemplo.com.br"),
            ("www.exemplo.com.br", "exemplo.com.br"),
            ("https://exemplo.com.br:8443/x?y=1#z", "exemplo.com.br"),
            ("https://user:senha@exemplo.com.br/", "exemplo.com.br"),
            ("  https://exemplo.com.br  ", "exemplo.com.br"),
            ("https://sub.exemplo.com.br", "sub.exemplo.com.br"),
        ],
    )
    def test_extrai_o_dominio(self, entrada, esperado):
        assert normalize_domain(entrada) == esperado

    def test_credencial_embutida_nao_vaza_para_o_dominio(self):
        """`user:senha@host` no banco seria segredo versionado por acidente."""
        assert "senha" not in (normalize_domain("https://user:senha@exemplo.com.br") or "")

    @pytest.mark.parametrize("invalido", ["", None, "localhost", "http://localhost:3000", "   "])
    def test_recusa_o_que_nao_e_dominio_de_empresa(self, invalido):
        assert normalize_domain(invalido) is None


class TestUrl:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("www.exemplo.com.br/", "https://www.exemplo.com.br/"),
            ("exemplo.com.br", "https://exemplo.com.br"),
            ("http://exemplo.com.br", "http://exemplo.com.br"),
            ("https://exemplo.com.br/a?b=1", "https://exemplo.com.br/a?b=1"),
            ("  exemplo.com.br  ", "https://exemplo.com.br"),
        ],
    )
    def test_completa_o_esquema_que_falta(self, entrada, esperado):
        """A tag `website` do OSM vem sem esquema na maioria das vezes."""
        assert normalize_url(entrada) == esperado

    @pytest.mark.parametrize(
        "perigosa",
        ["javascript:alert(1)", "data:text/html,<script>", "file:///etc/passwd", "ftp://x"],
    )
    def test_esquema_perigoso_e_recusado_e_nao_lavado(self, perigosa):
        """Testar por "://" faria `javascript:alert(1)` virar `https://javascript:alert(1)`."""
        assert normalize_url(perigosa) is None

    @pytest.mark.parametrize("invalida", ["", None, "   ", "//sem-esquema.com", "https://"])
    def test_recusa_o_que_nao_da_para_aproveitar(self, invalida):
        assert normalize_url(invalida) is None
