"""Persistência: retry com backoff no write do SQLite (NFR de resiliência).

A indisponibilidade é simulada trocando a conexão real por uma que falha
N vezes — assim o backoff é testado sem esperar tempo real.
"""
from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal

import pytest

from app.domain.models import CreditEvaluation, Status
from app.infrastructure.config import Settings
from app.infrastructure.persistence import (
    SqliteRepositorioAvaliacoes,
    construir_repositorio,
)


class ConexaoInstavel:
    """Envolve uma conexão real e falha `falhas` vezes em `execute`."""

    def __init__(self, real, falhas: int, erro: Exception) -> None:
        self._real = real
        self._falhas = falhas
        self._erro = erro
        self.tentativas_execute = 0
        self.fechada = False

    def execute(self, *args, **kwargs):
        self.tentativas_execute += 1
        if self.tentativas_execute <= self._falhas:
            raise self._erro
        return self._real.execute(*args, **kwargs)

    def commit(self):
        return self._real.commit()

    def close(self):
        self.fechada = True
        return self._real.close()


@pytest.fixture
def esperas() -> list[float]:
    """Sleeps registrados (segundos) — nenhum é realmente esperado."""
    return []


def _repo(tmp_path, esperas, **kwargs) -> SqliteRepositorioAvaliacoes:
    return SqliteRepositorioAvaliacoes(
        str(tmp_path / "avaliacoes.db"), dormir=esperas.append, **kwargs
    )


def _instavel(repo, falhas: int, erro: Exception | None = None) -> ConexaoInstavel:
    conn = ConexaoInstavel(
        repo._conn, falhas, erro or sqlite3.OperationalError("database is locked")
    )
    repo._conn = conn
    return conn


def _avaliacao(chave: str = "chave-1") -> CreditEvaluation:
    return CreditEvaluation(
        cpf_hash="hash-ana",
        status_final=Status.APROVADO,
        valor_liberado=Decimal("625.00"),
        motivos=[],
        regras_aplicadas=["ScoreMinimoRule"],
        idempotency_key=chave,
    )


def test_write_retenta_e_concede_na_segunda(tmp_path, esperas, caplog):
    repo = _repo(tmp_path, esperas, tentativas=3, backoff_ms=100)
    conn = _instavel(repo, falhas=1)

    with caplog.at_level(logging.WARNING, logger="credito_rotativo"):
        repo.salvar(_avaliacao())

    assert conn.tentativas_execute == 2
    assert esperas == [pytest.approx(0.1)]  # base 100ms na 1ª falha
    assert len(repo.listar()) == 1  # write real aconteceu
    eventos = [r.getMessage() for r in caplog.records if r.name == "credito_rotativo"]
    assert eventos == ["persistencia_retry"]
    assert caplog.records[0].contexto["tentativa"] == 1
    assert caplog.records[0].contexto["operacao"] == "salvar"
    repo.fechar()


def test_exaustao_propaga_o_erro_depois_de_tentar(tmp_path, esperas, caplog):
    repo = _repo(tmp_path, esperas, tentativas=3, backoff_ms=100)
    conn = _instavel(repo, falhas=99)

    with caplog.at_level(logging.WARNING, logger="credito_rotativo"):
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            repo.salvar(_avaliacao())

    assert conn.tentativas_execute == 3  # tentou todas
    assert esperas == [pytest.approx(0.1), pytest.approx(0.2)]  # 100 → 200
    eventos = [r.getMessage() for r in caplog.records if r.name == "credito_rotativo"]
    assert eventos == ["persistencia_retry", "persistencia_retry", "persistencia_falha"]
    repo.fechar()


def test_backoff_exponencial_respeita_o_teto(tmp_path, esperas):
    repo = _repo(
        tmp_path, esperas, tentativas=5, backoff_ms=100, backoff_max_ms=150
    )
    _instavel(repo, falhas=99)

    with pytest.raises(sqlite3.OperationalError):
        repo.salvar(_avaliacao())

    # 100 → 200(limitado em 150) → 400(150) → 800(150)
    assert esperas == [
        pytest.approx(0.1),
        pytest.approx(0.15),
        pytest.approx(0.15),
        pytest.approx(0.15),
    ]
    repo.fechar()


def test_erro_nao_transitorio_propaga_sem_repetir(tmp_path, esperas):
    """Só OperationalError é transitório: bug de programação não deve dormir."""
    repo = _repo(tmp_path, esperas, tentativas=5, backoff_ms=100)
    conn = _instavel(repo, falhas=99, erro=sqlite3.ProgrammingError("esperando '?'"))

    with pytest.raises(sqlite3.ProgrammingError):
        repo.salvar(_avaliacao())

    assert conn.tentativas_execute == 1
    assert esperas == []
    repo.fechar()


def test_abertura_com_retry_tambem(tmp_path, esperas, monkeypatch):
    """Boot com o banco indisponível (lock de outro processo, I/O) também retenta."""
    chamadas = {"n": 0}
    real_connect = sqlite3.connect

    def conecta_instavel(*args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(
        "app.infrastructure.persistence.sqlite3.connect", conecta_instavel
    )
    repo = SqliteRepositorioAvaliacoes(
        str(tmp_path / "avaliacoes.db"), dormir=esperas.append, tentativas=3
    )
    try:
        assert chamadas["n"] == 2
        assert esperas == [pytest.approx(0.1)]
        repo.salvar(_avaliacao())
        assert len(repo.listar()) == 1
    finally:
        repo.fechar()


def test_conexao_aberta_e_fechada_quando_o_schema_falha(tmp_path, esperas, monkeypatch):
    """Conectou mas o CREATE TABLE falhou: fecha antes de retentar (sem vazamento)."""
    real_connect = sqlite3.connect
    chamadas = {"n": 0}
    abertas: list[ConexaoInstavel] = []

    def conecta(*args, **kwargs):
        chamadas["n"] += 1
        conn = ConexaoInstavel(
            real_connect(*args, **kwargs),
            falhas=1 if chamadas["n"] == 1 else 0,
            erro=sqlite3.OperationalError("disk I/O error"),
        )
        abertas.append(conn)
        return conn

    monkeypatch.setattr("app.infrastructure.persistence.sqlite3.connect", conecta)
    repo = SqliteRepositorioAvaliacoes(
        str(tmp_path / "schema.db"), dormir=esperas.append, tentativas=3
    )
    try:
        assert chamadas["n"] == 2
        assert abertas[0].fechada  # a conexão da 1ª tentativa foi fechada
        assert not abertas[1].fechada
        assert esperas == [pytest.approx(0.1)]
        repo.salvar(_avaliacao())
        assert len(repo.listar()) == 1
    finally:
        repo.fechar()


def test_tentativa_minima_e_um(tmp_path):
    """tentativas=0 não pode deixar o write sem proteção."""
    repo = _repo(tmp_path, [], tentativas=0)
    assert repo._tentativas == 1
    repo.fechar()


def test_config_env_alimenta_o_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("CREDITO_PERSISTENCIA", "sqlite")
    monkeypatch.setenv("CREDITO_DB_PATH", str(tmp_path / "env.db"))
    monkeypatch.setenv("CREDITO_PERSISTENCIA_RETRY_TENTATIVAS", "7")
    monkeypatch.setenv("CREDITO_PERSISTENCIA_RETRY_BACKOFF_MS", "25")

    settings = Settings()
    assert settings.persistencia_retry_tentativas == 7
    assert settings.persistencia_retry_backoff_ms == 25

    repo = construir_repositorio(settings)
    try:
        assert isinstance(repo, SqliteRepositorioAvaliacoes)
        assert repo._tentativas == 7
        assert repo._backoff_ms == 25
    finally:
        repo.fechar()
