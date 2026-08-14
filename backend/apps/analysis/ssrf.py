"""Guard de SSRF — o único caminho pelo qual este projeto busca URL de terceiro.

## Por que isto existe

O analisador recebe URLs que vieram do OpenStreetMap, de outras fontes e, no futuro, do
próprio usuário. Ele as busca a partir de um worker que roda **dentro da rede da aplicação**,
com alcance ao Postgres, ao Redis e, em nuvem, ao endpoint de metadata que entrega
credenciais da instância. Uma URL hostil aponta o worker para dentro de casa.

Validar a string antes de conectar **não basta** (SECURITY.md). Dois furos derrubam essa
abordagem:

- **TOCTOU / DNS rebinding**: o nome resolve para um IP público na validação e para
  `127.0.0.1` um instante depois, quando a biblioteca resolve de novo para conectar.
- **Redirect**: cada `301` é uma URL nova, escolhida pelo servidor remoto, que nunca passou
  por validação nenhuma.

Por isso aqui a conexão é feita **no IP já validado**, e cada redirect é revalidado do zero.

## Por que sem `requests` ou `httpx`

Nenhuma das duas conecta num IP mandando `Host` de outro nome sem um adaptador ou transporte
escrito à mão. A parte difícil continuaria sendo nossa; a dependência só acrescentaria
superfície. `http.client` + `ssl` da stdlib fazem exatamente o necessário.
"""

from __future__ import annotations

import http.client
import ipaddress
import logging
import socket
import ssl
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings

logger = logging.getLogger(__name__)

ESQUEMAS_PERMITIDOS = ("http", "https")
PORTAS_PADRAO = {"http": 80, "https": 443}

# Nomes que não precisam nem chegar ao DNS.
NOMES_BLOQUEADOS = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


class SSRFBlockedError(Exception):
    """A URL foi recusada pelo guard. Nunca é 'site fora do ar' — é tentativa barrada."""


class FetchError(Exception):
    """A URL passou pelo guard, mas a busca falhou (timeout, conexão, HTTP inválido)."""


@dataclass
class SafeResponse:
    """O que uma busca segura devolveu."""

    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    redirect_count: int = 0
    elapsed_ms: int = 0
    is_https: bool = False
    has_valid_cert: bool = False
    truncated: bool = False
    chain: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Corpo como texto, tolerante: página real vem com encoding errado o tempo todo."""
        return self.body.decode("utf-8", errors="replace")


def _ip_e_proibido(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Devolve o motivo da recusa, ou `None` se o IP é aceitável.

    A ordem importa menos que a cobertura: qualquer endereço que não seja global e roteável
    na internet pública é recusado. Preferir uma lista de proibidos a uma de permitidos seria
    errar por omissão — `is_global` erra fechado.
    """
    # IPv4 embrulhado em IPv6 (`::ffff:127.0.0.1`) é o furo clássico de quem só testa a forma
    # IPv4: o endereço parece v6, escapa das checagens de v4 e chega no loopback.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        interno = _ip_e_proibido(ip.ipv4_mapped)
        return f"IPv4 mapeado em IPv6 ({ip.ipv4_mapped}): {interno}" if interno else None

    # A ordem vai do mais específico para o mais genérico, e não é cosmética: no `ipaddress`
    # do Python, link-local, loopback e reservado **também** são `is_private`. Checar
    # `is_private` primeiro bloquearia igual, mas relataria "endereço privado" para quem
    # sondou o metadata da nuvem — e aí o log perde justamente o sinal que importa.
    if ip.is_loopback:
        return f"{ip} é loopback"
    if ip.is_link_local:
        # Inclui 169.254.169.254, o metadata das nuvens — o alvo mais valioso de um SSRF.
        return f"{ip} é link-local (inclui metadata de nuvem)"
    if ip.is_multicast:
        return f"{ip} é multicast"
    if ip.is_reserved:
        return f"{ip} é reservado"
    if ip.is_unspecified:
        return f"{ip} não é especificado"
    if ip.is_private:
        # Cobre 10/8, 172.16/12, 192.168/16, fc00::/7 e também 0.0.0.0/8.
        return f"{ip} é endereço privado"
    if not ip.is_global:
        return f"{ip} não é roteável na internet pública"
    return None


def resolve_and_validate(host: str, port: int) -> list[str]:
    """Resolve o nome e devolve os IPs, **desde que todos** sejam aceitáveis.

    Todos, e não o primeiro: um DNS hostil devolve uma lista com um IP público na frente e
    `127.0.0.1` atrás, contando que o cliente valide um e conecte no outro.
    """
    if host.lower() in NOMES_BLOQUEADOS:
        raise SSRFBlockedError(f"Host bloqueado: {host!r}")

    # Um IP escrito direto na URL não passa pelo DNS, mas passa pela mesma validação.
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if motivo := _ip_e_proibido(literal):
            raise SSRFBlockedError(f"Destino recusado: {motivo}")
        return [str(literal)]

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise FetchError(f"Não foi possível resolver {host!r}: {exc}") from exc

    if not infos:
        raise FetchError(f"{host!r} não resolveu para nenhum endereço.")

    ips: list[str] = []
    for info in infos:
        # `sockaddr` é tupla de forma variável entre IPv4 e IPv6; o endereço é sempre o [0].
        endereco = str(info[4][0])
        ip = ipaddress.ip_address(endereco)
        if motivo := _ip_e_proibido(ip):
            raise SSRFBlockedError(f"{host} resolve para endereço proibido — {motivo}")
        ips.append(endereco)

    return ips


def _abrir_conexao(ip: str, host: str, port: int, https: bool, timeout: float):
    """Conecta **no IP validado**, apresentando o `host` original.

    É aqui que o TOCTOU morre. O socket é aberto à mão contra o IP que acabou de ser
    aprovado; o `server_hostname` do TLS continua sendo o nome, para que SNI e validação de
    certificado funcionem como devem. A `HTTPConnection` recebe o socket já pronto e por
    isso nunca chama `connect()` — ou seja, nunca resolve o nome de novo.
    """
    sock = socket.create_connection((ip, port), timeout=timeout)
    try:
        if https:
            contexto = ssl.create_default_context()
            sock = contexto.wrap_socket(sock, server_hostname=host)
        conexao = (
            http.client.HTTPSConnection(host, port)
            if https
            else http.client.HTTPConnection(host, port)
        )
        conexao.sock = sock
        return conexao
    except Exception:
        sock.close()
        raise


def _ler_com_teto(resposta, limite: int) -> tuple[bytes, bool]:
    """Lê em pedaços e corta no limite. `read()` cru aceitaria um corpo de qualquer tamanho."""
    pedacos: list[bytes] = []
    total = 0
    while total < limite:
        pedaco = resposta.read(min(65536, limite - total))
        if not pedaco:
            return b"".join(pedacos), False
        pedacos.append(pedaco)
        total += len(pedaco)
    return b"".join(pedacos), True


def safe_get(url: str, *, max_redirects: int | None = None) -> SafeResponse:
    """Busca `url` com todas as proteções do SECURITY.md.

    Levanta `SSRFBlockedError` quando o destino é proibido e `FetchError` quando é legítimo
    mas inalcançável. Distinguir os dois importa: o primeiro é uma tentativa barrada, que
    precisa aparecer como tal; o segundo é só um site fora do ar.
    """
    teto_redirects = settings.WEBSITE_SCAN_MAX_REDIRECTS if max_redirects is None else max_redirects
    timeout = settings.WEBSITE_SCAN_TIMEOUT_SECONDS
    limite_bytes = settings.WEBSITE_SCAN_MAX_BYTES

    atual = url
    cadeia: list[str] = []
    comeco = time.monotonic()

    for salto in range(teto_redirects + 1):
        partes = urlsplit(atual)

        if partes.scheme not in ESQUEMAS_PERMITIDOS:
            raise SSRFBlockedError(f"Esquema não permitido: {partes.scheme!r}. Só http e https.")
        if not partes.hostname:
            raise SSRFBlockedError(f"URL sem host: {atual!r}")

        https = partes.scheme == "https"
        porta = partes.port or PORTAS_PADRAO[partes.scheme]
        host = partes.hostname

        # Revalidação completa a cada salto: um redirect é uma URL escolhida pelo servidor
        # remoto, e ela nunca passou por validação nenhuma.
        ips = resolve_and_validate(host, porta)
        cadeia.append(atual)

        caminho = urlunsplit(("", "", partes.path or "/", partes.query, ""))
        conexao = _abrir_conexao(ips[0], host, porta, https, timeout)
        try:
            conexao.request(
                "GET",
                caminho,
                headers={
                    "Host": host,
                    "User-Agent": settings.WEBSITE_SCAN_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Encoding": "identity",
                },
            )
            resposta = conexao.getresponse()
            cabecalhos = {k.lower(): v for k, v in resposta.getheaders()}

            if resposta.status in (301, 302, 303, 307, 308):
                destino = cabecalhos.get("location")
                if not destino:
                    raise FetchError(f"Redirect {resposta.status} sem Location.")
                if salto == teto_redirects:
                    raise FetchError(f"Mais de {teto_redirects} redirects.")
                atual = _juntar(atual, destino)
                continue

            corpo, cortado = _ler_com_teto(resposta, limite_bytes)
            return SafeResponse(
                final_url=atual,
                status=resposta.status,
                headers=cabecalhos,
                body=corpo,
                redirect_count=salto,
                elapsed_ms=int((time.monotonic() - comeco) * 1000),
                is_https=https,
                # Chegar até aqui em HTTPS já significa que o `wrap_socket` validou a cadeia
                # e o nome — o contexto padrão do Python não é permissivo.
                has_valid_cert=https,
                truncated=cortado,
                chain=cadeia,
            )
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError(f"Falha ao buscar {atual}: {exc}") from exc
        finally:
            conexao.close()

    raise FetchError(f"Mais de {teto_redirects} redirects.")  # pragma: no cover - laço sai antes


def _juntar(base: str, destino: str) -> str:
    """Resolve o `Location` contra a URL atual, recusando esquema estranho.

    `urljoin` da stdlib resolveria `javascript:` ou `file:` sem reclamar; a checagem de
    esquema acontece no topo do laço, então basta não deixar passar um destino absoluto de
    esquema proibido disfarçado de relativo.
    """
    from urllib.parse import urljoin

    juntado = urljoin(base, destino)
    esquema = urlsplit(juntado).scheme
    if esquema not in ESQUEMAS_PERMITIDOS:
        raise SSRFBlockedError(f"Redirect para esquema não permitido: {esquema!r}")
    return juntado
