"""Observabilidade: logs estruturados (JSON por linha) + métricas em memória.

LGPD: logs sem PII — o CPF aparece apenas como hash e o nome nunca é
logado. `correlation_id` = idempotency_key, rastreia a avaliação de
ponta a ponta (submissão → cadeia → decisão).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("credito_rotativo")


class FormatoEstruturado(logging.Formatter):
    """Um evento JSON por linha — pronto para Loki/ELK/CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "evento": record.getMessage(),
        }
        contexto = getattr(record, "contexto", None)
        if contexto:
            payload.update(contexto)
        return json.dumps(payload, ensure_ascii=False)


def configurar_logging(nivel: str = "INFO") -> None:
    """Instala o handler estruturado (idempotente)."""
    logger.setLevel(nivel.upper())
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(FormatoEstruturado())
        logger.addHandler(handler)


def log_evento(evento: str, nivel: int = logging.INFO, **contexto) -> None:
    """Emite um evento estruturado. Contexto = campos do JSON (sem PII)."""
    logger.log(nivel, evento, extra={"contexto": contexto})


class Metricas:
    """Métricas em memória: volume, taxa de aprovação, latência p50/p95."""

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
