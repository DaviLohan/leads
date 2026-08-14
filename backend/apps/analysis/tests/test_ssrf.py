"""Testes do guard de SSRF.

O `SECURITY.md` é explícito: *"Testes de SSRF são pré-requisito para o scanner existir — o
código de scan não vai para a branch principal sem eles."* Este arquivo é essa condição.

Nada de rede: `getaddrinfo` é dublado para simular o DNS, inclusive DNS hostil. Cada teste
aqui corresponde a uma forma conhecida de escapar do guard.
"""

import ipaddress
import socket

import pytest
from django.test import override_settings

from apps.analysis.ssrf import (
    FetchError,
    SSRFBlockedError,
    _ip_e_proibido,
    resolve_and_validate,
    safe_get,
)


def dublar_dns(monkeypatch, *ips: str):
    """Faz `getaddrinfo` devolver exatamente estes IPs, na ordem."""

    def falso(host, port, *a, **k):
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (ip, port),
            )
            for ip in ips
        ]

    monkeypatch.setattr(socket, "getaddrinfo", falso)


class TestEsquema:
    """Regra 1: só http e https."""

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://127.0.0.1:6379/_INFO",
            "ftp://interno/segredo",
            "data:text/html,<script>",
            "jar:http://x/!/",
        ],
    )
    def test_recusa_esquema_perigoso(self, url):
        with pytest.raises(SSRFBlockedError, match="Esquema não permitido|URL sem host"):
            safe_get(url)

    def test_recusa_url_sem_host(self):
        with pytest.raises(SSRFBlockedError):
            safe_get("http:///caminho")


class TestFaixasDeIP:
    """Regra 3: todas as faixas que não são internet pública."""

    @pytest.mark.parametrize(
        ("ip", "motivo"),
        [
            ("127.0.0.1", "loopback"),
            ("127.255.255.254", "loopback"),
            ("10.0.0.1", "privado"),
            ("172.16.0.1", "privado"),
            ("172.31.255.254", "privado"),
            ("192.168.1.1", "privado"),
            ("0.0.0.0", "não é especificado"),  # noqa: S104 - é o alvo do bloqueio
            ("169.254.1.1", "link-local"),
            ("169.254.169.254", "link-local"),  # metadata de nuvem
            ("224.0.0.1", "multicast"),
            ("240.0.0.1", "reservado"),
            ("::1", "loopback"),
            ("fc00::1", "privado"),
            ("fe80::1", "link-local"),
            ("ff02::1", "multicast"),
        ],
    )
    def test_bloqueia(self, ip, motivo):
        resultado = _ip_e_proibido(ipaddress.ip_address(ip))
        assert resultado is not None, f"{ip} passou!"
        assert motivo in resultado

    @pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "200.160.2.3", "2001:4860:4860::8888"])
    def test_deixa_passar_ip_publico(self, ip):
        assert _ip_e_proibido(ipaddress.ip_address(ip)) is None

    @pytest.mark.parametrize(
        "ip", ["::ffff:127.0.0.1", "::ffff:169.254.169.254", "::ffff:10.0.0.1"]
    )
    def test_ipv4_mapeado_em_ipv6_nao_escapa(self, ip):
        """O furo clássico: parece IPv6, escapa das checagens de v4, chega no loopback."""
        resultado = _ip_e_proibido(ipaddress.ip_address(ip))
        assert resultado is not None, f"{ip} passou!"
        assert "mapeado" in resultado


class TestResolucao:
    """Regra 2: validar todos os IPs, não o primeiro."""

    def test_dns_que_devolve_publico_e_privado_e_recusado(self, monkeypatch):
        """DNS hostil põe o público na frente contando que só ele seja checado."""
        dublar_dns(monkeypatch, "8.8.8.8", "127.0.0.1")

        with pytest.raises(SSRFBlockedError, match="proibido"):
            resolve_and_validate("malicioso.exemplo", 80)

    def test_privado_na_frente_tambem_e_recusado(self, monkeypatch):
        dublar_dns(monkeypatch, "10.0.0.1", "8.8.8.8")
        with pytest.raises(SSRFBlockedError):
            resolve_and_validate("malicioso.exemplo", 80)

    def test_todos_publicos_passa(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8", "1.1.1.1")
        assert resolve_and_validate("bom.exemplo", 80) == ["8.8.8.8", "1.1.1.1"]

    @pytest.mark.parametrize("nome", ["localhost", "LOCALHOST", "localhost.localdomain"])
    def test_localhost_nem_chega_ao_dns(self, nome, monkeypatch):
        def explodir(*a, **k):  # pragma: no cover - não deve ser chamado
            raise AssertionError("não devia resolver")

        monkeypatch.setattr(socket, "getaddrinfo", explodir)
        with pytest.raises(SSRFBlockedError, match="Host bloqueado"):
            resolve_and_validate(nome, 80)

    def test_ip_literal_na_url_passa_pela_mesma_validacao(self, monkeypatch):
        def explodir(*a, **k):  # pragma: no cover - não deve ser chamado
            raise AssertionError("IP literal não precisa de DNS")

        monkeypatch.setattr(socket, "getaddrinfo", explodir)
        with pytest.raises(SSRFBlockedError, match="loopback"):
            resolve_and_validate("127.0.0.1", 80)

    def test_nome_que_nao_resolve_e_falha_de_busca_e_nao_bloqueio(self, monkeypatch):
        """Distinguir importa: bloqueio é ataque barrado, falha é site fora do ar."""
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("nxdomain")),
        )
        with pytest.raises(FetchError):
            resolve_and_validate("nao-existe.exemplo", 80)


class TestConexaoNoIpValidado:
    """Regra 4: conectar no IP aprovado, não deixar a lib resolver de novo."""

    def test_conecta_no_ip_que_foi_validado(self, monkeypatch):
        """Se conectasse pelo nome, o DNS poderia ter mudado entre a checagem e a conexão."""
        dublar_dns(monkeypatch, "8.8.8.8")
        conectados = []

        from apps.analysis import ssrf

        class SocketFalso:
            def close(self):
                pass

        def falso_create_connection(endereco, timeout=None):
            conectados.append(endereco)
            return SocketFalso()

        class ConexaoFalsa:
            def __init__(self, *a, **k):
                self.sock = None

            def request(self, *a, **k):
                pass

            def getresponse(self):
                class R:
                    status = 200

                    def getheaders(self):
                        return [("Content-Type", "text/html")]

                    def read(self, n):
                        return b""

                return R()

            def close(self):
                pass

        monkeypatch.setattr(ssrf.socket, "create_connection", falso_create_connection)
        monkeypatch.setattr(ssrf.http.client, "HTTPConnection", ConexaoFalsa)

        safe_get("http://bom.exemplo/pagina")

        assert conectados == [("8.8.8.8", 80)], "conectou no nome em vez do IP validado"


class TestRedirects:
    """Regras 5 e 7: revalidar cada salto, teto de 3, sem esquema estranho."""

    def _dublar_respostas(self, monkeypatch, respostas):
        """Cada item: (status, headers) — encadeia as respostas na ordem."""
        from apps.analysis import ssrf

        estado = {"i": 0}

        class SocketFalso:
            def close(self):
                pass

        class ConexaoFalsa:
            def __init__(self, *a, **k):
                self.sock = None

            def request(self, *a, **k):
                pass

            def getresponse(self):
                status, cabecalhos = respostas[estado["i"]]
                estado["i"] += 1

                class R:
                    def __init__(self):
                        self.status = status

                    def getheaders(self):
                        return list(cabecalhos.items())

                    def read(self, n):
                        return b""

                return R()

            def close(self):
                pass

        monkeypatch.setattr(ssrf.socket, "create_connection", lambda *a, **k: SocketFalso())
        monkeypatch.setattr(ssrf.http.client, "HTTPConnection", ConexaoFalsa)

    def test_redirect_para_ip_privado_e_bloqueado(self, monkeypatch):
        """O caso que motiva revalidar: o servidor remoto escolhe o próximo destino."""
        dublar_dns(monkeypatch, "8.8.8.8")
        self._dublar_respostas(monkeypatch, [(302, {"Location": "http://127.0.0.1:6379/"})])

        with pytest.raises(SSRFBlockedError, match="loopback"):
            safe_get("http://bom.exemplo/")

    def test_redirect_para_metadata_e_bloqueado(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8")
        self._dublar_respostas(
            monkeypatch, [(302, {"Location": "http://169.254.169.254/latest/meta-data/"})]
        )

        with pytest.raises(SSRFBlockedError, match="link-local"):
            safe_get("http://bom.exemplo/")

    def test_redirect_para_esquema_proibido_e_bloqueado(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8")
        self._dublar_respostas(monkeypatch, [(302, {"Location": "file:///etc/passwd"})])

        with pytest.raises(SSRFBlockedError, match="esquema não permitido"):
            safe_get("http://bom.exemplo/")

    @override_settings(WEBSITE_SCAN_MAX_REDIRECTS=2)
    def test_acima_do_teto_de_saltos(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8")
        self._dublar_respostas(
            monkeypatch,
            [
                (302, {"Location": "http://bom.exemplo/a"}),
                (302, {"Location": "http://bom.exemplo/b"}),
                (302, {"Location": "http://bom.exemplo/c"}),
            ],
        )

        with pytest.raises(FetchError, match="redirects"):
            safe_get("http://bom.exemplo/")

    def test_cadeia_legitima_passa_e_conta_os_saltos(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8")
        self._dublar_respostas(
            monkeypatch,
            [
                (301, {"Location": "http://bom.exemplo/novo"}),
                (200, {"Content-Type": "text/html"}),
            ],
        )

        resposta = safe_get("http://bom.exemplo/velho")

        assert resposta.status == 200
        assert resposta.redirect_count == 1
        assert resposta.final_url == "http://bom.exemplo/novo"
        assert len(resposta.chain) == 2

    def test_redirect_sem_location_e_falha(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8")
        self._dublar_respostas(monkeypatch, [(302, {})])

        with pytest.raises(FetchError, match="sem Location"):
            safe_get("http://bom.exemplo/")


class TestTetoDeBytes:
    """Regra 6: corte por streaming, não `read()` no corpo inteiro."""

    @override_settings(WEBSITE_SCAN_MAX_BYTES=100)
    def test_corta_corpo_gigante(self, monkeypatch):
        dublar_dns(monkeypatch, "8.8.8.8")
        from apps.analysis import ssrf

        class SocketFalso:
            def close(self):
                pass

        class ConexaoFalsa:
            def __init__(self, *a, **k):
                self.sock = None

            def request(self, *a, **k):
                pass

            def getresponse(self):
                class R:
                    status = 200

                    def getheaders(self):
                        return [("Content-Type", "text/html")]

                    def read(self, n):
                        # Um servidor hostil serve para sempre; o corte é nosso.
                        return b"x" * n

                return R()

            def close(self):
                pass

        monkeypatch.setattr(ssrf.socket, "create_connection", lambda *a, **k: SocketFalso())
        monkeypatch.setattr(ssrf.http.client, "HTTPConnection", ConexaoFalsa)

        resposta = safe_get("http://bom.exemplo/")

        assert len(resposta.body) == 100
        assert resposta.truncated is True
