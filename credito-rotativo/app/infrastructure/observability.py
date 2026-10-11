"""Observabilidade: logs estruturados (via logging padrão) + métricas em memória.

Métricas: volume de avaliações, taxa de aprovação/reprovação, latência p50/p95.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger("credito_rotativo")


class Metricas:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.aprovacoes = 0
        self.reprovacoes = 0
        self._latencias_ms: list[float] = []

    def registrar(self, aprovado: bool) -> None:
        with self._lock:
            self.total += 1
            if aprovado:
                self.aprovacoes += 1
            else:
                self.reprovacoes += 1

    def registrar_latencia(self, latencia_ms: float) -> None:
        with self._lock:
            self._latencias_ms.append(latencia_ms)

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self._latencias_ms)
            return {
                "total": self.total,
                "aprovacoes": self.aprovacoes,
                "reprovacoes": self.reprovacoes,
                "taxa_aprovacao": round(self.aprovacoes / self.total, 4) if self.total else 0.0,
                "latencia_p50_ms": round(lat[len(lat) // 2], 2) if lat else 0.0,
                "latencia_p95_ms": round(lat[int(len(lat) * 0.95)], 2) if lat else 0.0,
            }
