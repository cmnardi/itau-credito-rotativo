"""Persistência em memória (thread-safe). Troca trivial por SQLite/Postgres."""
from __future__ import annotations

import threading

from app.domain.models import CreditEvaluation


class RepositorioAvaliacoes:
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
