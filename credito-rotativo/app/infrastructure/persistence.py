"""Persistência: repositório em memória (padrão) ou SQLite (arquivo).

A interface é a mesma — `CREDITO_PERSISTENCIA` escolhe a
implementação sem mudar o caso de uso (seam para Postgres futuro).

O write do SQLite é protegido por **retry com backoff exponencial**
(NFR: resiliência a indisponibilidade temporária): erros transitórios
(`sqlite3.OperationalError` — banco travado, I/O) são retentados até
`CREDITO_PERSISTENCIA_RETRY_TENTATIVAS`, com espera `base × 2^(n−1)`
limitada por `..._BACKOFF_MAX_MS`. Cada tentativa vira log estruturado
(`persistencia_retry` em WARNING) e a exaustão, `persistencia_falha`
em ERROR — alimentando o alerta de taxa de erro do `/metricas`.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from decimal import Decimal

from app.domain.models import CreditEvaluation, Estado, Status
from app.infrastructure.config import Settings
from app.infrastructure.observability import log_evento


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
    a reinícios do serviço. Valores em TEXT para preservar o Decimal.

    `tentativas`/`backoff_ms`/`backoff_max_ms` vêm da configuração;
    `dormir` é injetável para testar o backoff sem esperar de verdade.
    """

    _ESQUEMA = """
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

    def __init__(
        self,
        caminho: str = "avaliacoes.db",
        *,
        tentativas: int = 3,
        backoff_ms: float = 100.0,
        backoff_max_ms: float = 2000.0,
        dormir=time.sleep,
    ) -> None:
        super().__init__()
        self._caminho = caminho
        self._tentativas = max(1, tentativas)
        self._backoff_ms = backoff_ms
        self._backoff_max_ms = backoff_max_ms
        self._dormir = dormir
        # Abertura também pode falhar por indisponibilidade transitória
        # (lock de outro processo no boot, I/O) — mesma política de retry.
        with self._lock:
            self._conn = self._com_retry("conectar", self._abrir_conexao)

    def _abrir_conexao(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._caminho, check_same_thread=False)
        try:
            conn.execute(self._ESQUEMA)
            conn.commit()
        except sqlite3.Error:
            conn.close()  # não vazar conexão entre tentativas
            raise
        return conn

    def _com_retry(self, operacao: str, funcao):
        """Executa `funcao`, retentando erros transitórios do SQLite.

        Backoff exponencial `backoff_ms × 2^(tentativa−1)` limitado por
        `backoff_max_ms`. Só `sqlite3.OperationalError` é transitório
        (banco travado, I/O); qualquer outro erro propaga na hora.
        O lock do repositório permanece tomado durante a espera para não
        intercalar escritas na mesma conexão.
        """
        for tentativa in range(1, self._tentativas + 1):
            try:
                return funcao()
            except sqlite3.OperationalError as exc:
                if tentativa >= self._tentativas:
                    log_evento(
                        "persistencia_falha",
                        logging.ERROR,
                        operacao=operacao,
                        tentativas=tentativa,
                        erro=str(exc),
                    )
                    raise
                espera_ms = min(
                    self._backoff_ms * (2 ** (tentativa - 1)),
                    self._backoff_max_ms,
                )
                log_evento(
                    "persistencia_retry",
                    logging.WARNING,
                    operacao=operacao,
                    tentativa=tentativa,
                    tentativas=self._tentativas,
                    backoff_ms=espera_ms,
                    erro=str(exc),
                )
                self._dormir(espera_ms / 1000)

    def salvar(self, avaliacao: CreditEvaluation) -> None:
        with self._lock:
            self._com_retry("salvar", lambda: self._gravar(avaliacao))

    def _gravar(self, avaliacao: CreditEvaluation) -> None:
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
        return SqliteRepositorioAvaliacoes(
            config.db_path,
            tentativas=config.persistencia_retry_tentativas,
            backoff_ms=config.persistencia_retry_backoff_ms,
            backoff_max_ms=config.persistencia_retry_backoff_max_ms,
        )
    return RepositorioAvaliacoes()
