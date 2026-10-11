"""Persistência: repositório em memória (padrão) ou SQLite (arquivo).

A interface é a mesma — `CREDITO_PERSISTENCIA` escolhe a
implementação sem mudar o caso de uso (seam para Postgres futuro).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from decimal import Decimal

from app.domain.models import CreditEvaluation, Estado, Status
from app.infrastructure.config import Settings


class RepositorioAvaliacoes:
    """Repositório em memória (thread-safe). Troca trivial por banco real."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._por_chave: dict[str, CreditEvaluation] = {}

    def salvar(self, avaliacao: CreditEvaluation) -> None:
        with self._lock:
            self._por_chave[avaliacao.idempotency_key] = avaliacao

    def buscar_por_chave(self, chave: str) -> CreditEvaluation | None:
        with self._lock:
            return self._por_chave.get(chave)

    def listar(self) -> list[CreditEvaluation]:
        with self._lock:
            return list(self._por_chave.values())


class SqliteRepositorioAvaliacoes(RepositorioAvaliacoes):
    """Repositório em SQLite (arquivo) — as avaliações sobrevivem
    a reinícios do serviço. Valores em TEXT para preservar o Decimal."""

    def __init__(self, caminho: str = "avaliacoes.db") -> None:
        super().__init__()
        self._caminho = caminho
        self._conn = sqlite3.connect(caminho, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS avaliacoes (
                idempotency_key TEXT PRIMARY KEY,
                cpf_hash        TEXT NOT NULL,
                status_final    TEXT NOT NULL,
                valor_liberado  TEXT NOT NULL,
                motivos         TEXT NOT NULL,
                regras_aplicadas TEXT NOT NULL,
                estado          TEXT NOT NULL,
                timestamp       TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def salvar(self, avaliacao: CreditEvaluation) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO avaliacoes VALUES (?,?,?,?,?,?,?,?)",
                self._para_linha(avaliacao),
            )
            self._conn.commit()

    def buscar_por_chave(self, chave: str) -> CreditEvaluation | None:
        with self._lock:
            linha = self._conn.execute(
                "SELECT * FROM avaliacoes WHERE idempotency_key = ?", (chave,)
            ).fetchone()
        return self._para_dominio(linha) if linha else None

    def listar(self) -> list[CreditEvaluation]:
        with self._lock:
            linhas = self._conn.execute("SELECT * FROM avaliacoes").fetchall()
        return [self._para_dominio(linha) for linha in linhas]

    def fechar(self) -> None:
        """Fecha a conexão (evita ResourceWarning em testes)."""
        self._conn.close()

    @staticmethod
    def _para_linha(a: CreditEvaluation) -> tuple:
        return (
            a.idempotency_key,
            a.cpf_hash,
            a.status_final.value,
            str(a.valor_liberado),
            json.dumps(a.motivos),
            json.dumps(a.regras_aplicadas),
            a.estado.value,
            a.timestamp.isoformat(),
        )

    @staticmethod
    def _para_dominio(linha: tuple) -> CreditEvaluation:
        return CreditEvaluation(
            idempotency_key=linha[0],
            cpf_hash=linha[1],
            status_final=Status(linha[2]),
            valor_liberado=Decimal(linha[3]),
            motivos=json.loads(linha[4]),
            regras_aplicadas=json.loads(linha[5]),
            estado=Estado(linha[6]),
            timestamp=datetime.fromisoformat(linha[7]),
        )


def construir_repositorio(config: Settings) -> RepositorioAvaliacoes:
    """Seleciona a persistência via configuração (env var)."""
    if config.persistencia == "sqlite":
        return SqliteRepositorioAvaliacoes(config.db_path)
    return RepositorioAvaliacoes()
