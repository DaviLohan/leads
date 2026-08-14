"""Cliente do IBGE — retry, gzip e teto de tamanho, sem tocar a rede.

`urlopen` é substituído por um dublê. Nenhum teste do projeto sai para a internet
(CLAUDE.md), e mesmo assim estes caminhos precisam ser exercitados: são eles que decidem
se uma falha do IBGE vira retry, erro claro ou corrupção silenciosa.
"""

import gzip
import json

import pytest
from django.test import override_settings

from apps.geography import ibge


class RespostaFalsa:
    """Mínimo que `_read_body` usa: `read(n)` e protocolo de context manager."""

    def __init__(self, corpo: bytes):
        self._corpo = corpo

    def read(self, tamanho: int) -> bytes:
        return self._corpo[:tamanho]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def sem_espera(monkeypatch):
    """Neutraliza o backoff: o teste verifica a lógica, não a passagem do tempo."""
    esperas = []
    monkeypatch.setattr(ibge.time, "sleep", esperas.append)
    return esperas


def _responder(monkeypatch, *respostas):
    """Faz `urlopen` devolver (ou levantar) cada item de `respostas`, em ordem."""
    chamadas = []

    def falso_urlopen(request, timeout=None):
        chamadas.append(request.full_url)
        resultado = respostas[len(chamadas) - 1]
        if isinstance(resultado, Exception):
            raise resultado
        return RespostaFalsa(resultado)

    monkeypatch.setattr(ibge.urllib.request, "urlopen", falso_urlopen)
    return chamadas


def test_le_json_simples(monkeypatch):
    _responder(monkeypatch, json.dumps([{"id": 41}]).encode())
    assert ibge.fetch_states() == [{"id": 41}]


def test_descomprime_resposta_gzipada(monkeypatch):
    """O IBGE comprime mesmo com `Accept-Encoding: identity`, e o urllib não descomprime."""
    _responder(monkeypatch, gzip.compress(json.dumps([{"id": 4113700}]).encode()))
    assert ibge.fetch_cities() == [{"id": 4113700}]


def test_monta_a_url_a_partir_do_settings(monkeypatch):
    chamadas = _responder(monkeypatch, b"[]")
    ibge.fetch_cities()
    assert chamadas == ["https://servicodados.ibge.gov.br/api/v1/localidades/municipios"]


@override_settings(IBGE_MAX_BYTES=10)
def test_recusa_resposta_acima_do_teto(monkeypatch):
    """Entrada de rede sem teto carregaria o que viesse na memória do worker."""
    _responder(monkeypatch, b"x" * 11)
    with pytest.raises(ibge.IBGEError, match="passou de 10 bytes"):
        ibge.fetch_states()


@override_settings(IBGE_MAX_BYTES=10)
def test_aceita_resposta_exatamente_no_teto(monkeypatch):
    """Ler um byte além do limite é o que separa "no limite" de "estourou"."""
    _responder(monkeypatch, b"[1,2,3,4]")
    assert ibge.fetch_states() == [1, 2, 3, 4]


@override_settings(IBGE_API_URL="file:///etc/passwd")
def test_recusa_esquema_que_nao_seja_http(monkeypatch):
    """Um IBGE_API_URL mal preenchido não pode virar leitura de disco."""
    chamadas = _responder(monkeypatch, b"[]")
    with pytest.raises(ibge.IBGEError, match="Esquema não permitido"):
        ibge.fetch_states()
    assert chamadas == []


def test_tenta_de_novo_e_tem_sucesso(monkeypatch, sem_espera):
    chamadas = _responder(monkeypatch, OSError("conexão recusada"), b"[]")
    assert ibge.fetch_states() == []
    assert len(chamadas) == 2
    assert len(sem_espera) == 1


def test_desiste_depois_do_limite_de_tentativas(monkeypatch, sem_espera):
    """Retry limitado, nunca infinito (CLAUDE.md)."""
    falhas = [OSError("timeout")] * 3
    chamadas = _responder(monkeypatch, *falhas)

    with pytest.raises(ibge.IBGEError, match="após 3 tentativas"):
        ibge.fetch_states()

    assert len(chamadas) == 3  # IBGE_MAX_ATTEMPTS
    assert len(sem_espera) == 2  # não dorme depois da última


def test_backoff_cresce_entre_as_tentativas(monkeypatch, sem_espera):
    """Com o jitter fixado, a espera tem de dobrar a cada tentativa.

    Comparar `segunda > primeira` com o jitter solto seria flaky de verdade: o fator vive
    em [0.5, 1.5), então um sorteio alto na primeira e baixo na segunda inverte a ordem
    (1 * 1,4 > 2 * 0,51). Fixar o sorteio testa o expoente, que é o que importa aqui.
    """
    monkeypatch.setattr(ibge.random, "random", lambda: 0.5)  # jitter = 1.0
    _responder(monkeypatch, OSError("1"), OSError("2"), b"[]")
    ibge.fetch_states()

    assert sem_espera == [ibge.BACKOFF_BASE_SECONDS, ibge.BACKOFF_BASE_SECONDS * 2]


def test_json_invalido_tambem_e_motivo_de_retry(monkeypatch, sem_espera):
    """Resposta truncada é a mesma coisa que erro de rede: o dado não veio."""
    _responder(monkeypatch, b"{nao e json", b"[]")
    assert ibge.fetch_states() == []
    assert len(sem_espera) == 1


def test_gzip_corrompido_nao_passa_como_dado_bom(monkeypatch, sem_espera):
    """Começa com o magic do gzip mas não descomprime — tem de falhar, não silenciar."""
    _responder(monkeypatch, ibge.GZIP_MAGIC + b"lixo", ibge.GZIP_MAGIC + b"lixo", b"[]")
    assert ibge.fetch_states() == []
    assert len(sem_espera) == 2
