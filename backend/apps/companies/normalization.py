"""Normalização dos identificadores de uma empresa.

Todo dado que chega de fora vem sujo: CNPJ com máscara, telefone com DDD faltando, URL
com `www` e caixa alta. Guardar a forma normalizada em coluna própria é o que permite
comparar, deduplicar (Etapa 6) e suprimir contato (Etapa 12) sem normalizar de novo a cada
consulta — o que não usaria índice.

Toda função aqui devolve `None` para entrada que não dá para normalizar, nunca a entrada
crua e nunca string vazia. Quem chama decide se `None` é erro ou campo opcional; o que não
pode é um valor meio normalizado entrar no banco e quebrar a unicidade em silêncio.

`providers` (Etapa 7) e `crm` (Etapa 12) importam daqui — ambos estão acima de `companies`
na ordem de dependência do CLAUDE.md, então a direção se mantém.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import phonenumbers

SOMENTE_DIGITOS = re.compile(r"\D")
# Um esquema de URL segundo a RFC 3986: letra seguida de letras, dígitos, +, - ou ponto.
ESQUEMA_NO_INICIO = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")

# Pesos do módulo 11 usados pela Receita Federal nos dois dígitos verificadores.
PESOS_PRIMEIRO_DV = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
PESOS_SEGUNDO_DV = [6, *PESOS_PRIMEIRO_DV]


def _digito_verificador(digitos: str, pesos: list[int]) -> str:
    resto = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True)) % 11
    return "0" if resto < 2 else str(11 - resto)


def normalize_tax_id(value: str | None) -> str | None:
    """Devolve o CNPJ com 14 dígitos, sem máscara, ou `None` se for inválido.

    >>> normalize_tax_id("11.222.333/0001-81")
    '11222333000181'
    >>> normalize_tax_id("11222333000182") is None
    True

    Os dígitos verificadores são conferidos de propósito: CNPJ é chave de deduplicação
    (o sinal mais forte depois de provider+external_id), e um dígito trocado numa fonte
    ruim fundiria duas empresas diferentes. Melhor recusar do que aceitar errado.

    Repetição do mesmo dígito (00000000000000) passa no módulo 11 por acidente aritmético
    e precisa de recusa explícita.
    """
    if not value:
        return None

    digitos = SOMENTE_DIGITOS.sub("", value)
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return None

    esperado = _digito_verificador(digitos[:12], PESOS_PRIMEIRO_DV)
    esperado += _digito_verificador(digitos[:13], PESOS_SEGUNDO_DV)
    return digitos if digitos[12:] == esperado else None


def normalize_phone(value: str | None, region: str = "BR") -> str | None:
    """Devolve o telefone em E.164 (`+5543999998888`), ou `None` se não for válido.

    >>> normalize_phone("(43) 99999-8888")
    '+5543999998888'

    A `phonenumbers` decide o que é válido: faixa de DDD, oito ou nove dígitos, fixo ou
    móvel. Escrever essa tabela à mão envelheceria mal — a numeração brasileira mudou mais
    de uma vez, e vai mudar de novo.

    E.164 é o formato que a supressão da LGPD exige (PROJECT_PLAN §3.4): sem um formato
    único, o mesmo telefone escrito de duas formas escaparia do opt-out.
    """
    if not value:
        return None

    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException:
        return None

    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_domain(value: str | None) -> str | None:
    """Extrai o domínio de uma URL, em minúsculas e sem `www.`.

    >>> normalize_domain("HTTPS://WWW.Exemplo.com.br/contato?x=1")
    'exemplo.com.br'
    >>> normalize_domain("exemplo.com.br")
    'exemplo.com.br'

    Aceita entrada sem esquema porque fonte externa manda das duas formas. Porta e
    credenciais embutidas (`user:senha@host`) são descartadas — o que interessa é a
    identidade do site, que é sinal de deduplicação.
    """
    if not value:
        return None

    texto = value.strip()
    if "//" not in texto:
        # `urlsplit` sem esquema joga tudo em `path` e devolve `netloc` vazio.
        texto = f"//{texto}"

    host = urlsplit(texto).netloc.lower()
    host = host.rpartition("@")[2]  # descarta user:senha@
    host = host.partition(":")[0]  # descarta a porta
    host = host.removeprefix("www.").rstrip(".")

    # Precisa sobrar algo com ponto: "localhost" ou "" não são domínio de empresa.
    return host if "." in host else None


def normalize_url(value: str | None) -> str | None:
    """Devolve uma URL absoluta em `https://`, ou `None` se não der para aproveitar.

    >>> normalize_url("www.exemplo.com.br/contato")
    'https://www.exemplo.com.br/contato'
    >>> normalize_url("http://exemplo.com.br")
    'http://exemplo.com.br'

    Fonte externa manda URL sem esquema o tempo todo — a tag `website` do OSM é assim na
    maioria das vezes. Guardar crua faz o guard de SSRF recusar depois, e um endereço mal
    formado acabaria classificado como tentativa de ataque em vez de dado sujo.

    O padrão é `https`, e não `http`: site que só atende em texto puro redireciona, e o
    scanner segue o redirect. O contrário — assumir `http` num site só-HTTPS — desperdiça um
    salto em toda visita.
    """
    if not value:
        return None

    texto = value.strip()
    if not texto:
        return None

    # Só prefixa o que realmente não tem esquema. Testar por `"://"` deixaria
    # `javascript:alert(1)` virar `https://javascript:alert(1)` — lavando um esquema
    # perigoso em vez de recusá-lo.
    if not ESQUEMA_NO_INICIO.match(texto):
        texto = f"https://{texto}"

    partes = urlsplit(texto)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        return None
    return texto
