"""Observabilidade: logs estruturados (JSON por linha) + métricas e alertas
em memória.

LGPD: logs sem PII — o CPF aparece apenas como hash e o nome nunca é
logado. `correlation_id` = idempotency_key, rastreia a avaliação de
ponta a ponta (submissão → cadeia → decisão).

Alertas (NFR "alertas para possíveis erros ou falhas"): limites vindos da
configuração (`CREDITO_ALERTA_*`), avaliados sobre o snapshot das métricas
e logados **apenas na transição** de estado — polling em `/metricas` não
gera spam de evento.
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


def _alerta(
    codigo: str, severidade: str, mensagem: str, valor: float, limite: float
) -> dict:
    return {
        "codigo": codigo,
        "severidade": severidade,
        "mensagem": mensagem,
        "valor": valor,
        "limite": limite,
    }


class Metricas:
    """Métricas em memória: volume, taxa de aprovação/reprovação, falhas de
    processamento e latência p50/p95 — a base dos alertas do `/metricas`.

    Os limites vêm da configuração (`CREDITO_ALERTA_*`); a avaliação é uma
    função pura do snapshot (testável sem simular tempo real) e cada alerta
    só loga quando o estado muda.
    """

    def __init__(
        self,
        limite_latencia_p95_ms: float = 1000.0,
        limite_taxa_erro: float = 0.05,
        limite_taxa_reprovacao: float = 0.90,
    ) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.aprovacoes = 0
        self.reprovacoes = 0
        self.falhas = 0
        self.ultimo_erro: str | None = None
        self._latencias_ms: list[float] = []
        self._limites = {
            "latencia_p95_ms": limite_latencia_p95_ms,
            "taxa_erro": limite_taxa_erro,
            "taxa_reprovacao": limite_taxa_reprovacao,
        }
        self._alertas_ativos: set[str] = set()

    def registrar(self, aprovado: bool) -> None:
        with self._lock:
            self.total += 1
            if aprovado:
                self.aprovacoes += 1
            else:
                self.reprovacoes += 1

    def registrar_falha(self, erro: str) -> None:
        """Exceção no pipeline (estado FALHA) — alimenta a taxa de erro."""
        with self._lock:
            self.falhas += 1
            self.ultimo_erro = erro

    def registrar_latencia(self, latencia_ms: float) -> None:
        with self._lock:
            self._latencias_ms.append(latencia_ms)

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self._latencias_ms)
            processado = self.total + self.falhas
            return {
                "total": self.total,
                "aprovacoes": self.aprovacoes,
                "reprovacoes": self.reprovacoes,
                "falhas": self.falhas,
                "taxa_aprovacao": round(self.aprovacoes / self.total, 4)
                if self.total
                else 0.0,
                "taxa_reprovacao": round(self.reprovacoes / self.total, 4)
                if self.total
                else 0.0,
                "taxa_erro": round(self.falhas / processado, 4) if processado else 0.0,
                "ultimo_erro": self.ultimo_erro,
                "latencia_p50_ms": round(lat[len(lat) // 2], 2) if lat else 0.0,
                "latencia_p95_ms": round(lat[int(len(lat) * 0.95)], 2) if lat else 0.0,
            }

    def avaliar_alertas(self, snapshot: dict) -> list[dict]:
        """Avalia o `snapshot` contra os limites e loga só as transições.

        `alerta_disparado` (WARNING) ao entrar e `alerta_encerrado` (INFO) ao
        sair: quem faz polling do `/metricas` não gera evento repetido.
        """
        alertas = self._avaliar(snapshot)
        with self._lock:
            ativos = {alerta["codigo"] for alerta in alertas}
            novos = [a for a in alertas if a["codigo"] not in self._alertas_ativos]
            encerrados = sorted(self._alertas_ativos - ativos)
            self._alertas_ativos = ativos
        for alerta in novos:
            log_evento(
                "alerta_disparado",
                logging.WARNING,
                codigo=alerta["codigo"],
                severidade=alerta["severidade"],
                valor=alerta["valor"],
                limite=alerta["limite"],
            )
        for codigo in encerrados:
            log_evento("alerta_encerrado", codigo=codigo)
        return alertas

    def _avaliar(self, snapshot: dict) -> list[dict]:
        """Regras de alerta — função pura do snapshot (NFR: erros e falhas)."""
        limite = self._limites
        alertas: list[dict] = []

        latencia = snapshot["latencia_p95_ms"]
        if latencia > limite["latencia_p95_ms"]:
            alertas.append(
                _alerta(
                    "latencia_p95_acima_do_slo",
                    "critico",
                    f"latência p95 {latencia:.2f}ms acima do limite "
                    f"{limite['latencia_p95_ms']:.2f}ms (NFR: ≤ 1s por avaliação)",
                    latencia,
                    limite["latencia_p95_ms"],
                )
            )

        taxa_erro = snapshot["taxa_erro"]
        if taxa_erro > limite["taxa_erro"]:
            ultima = snapshot.get("ultimo_erro") or "n/d"
            alertas.append(
                _alerta(
                    "taxa_de_erro_acima_do_limite",
                    "critico",
                    f"taxa de erro {taxa_erro:.2%} acima do limite "
                    f"{limite['taxa_erro']:.2%} — última falha: {ultima}",
                    taxa_erro,
                    limite["taxa_erro"],
                )
            )

        taxa_reprovacao = snapshot["taxa_reprovacao"]
        if taxa_reprovacao >= limite["taxa_reprovacao"]:
            alertas.append(
                _alerta(
                    "taxa_de_reprovacao_anomala",
                    "warning",
                    f"taxa de reprovação {taxa_reprovacao:.2%} >= "
                    f"{limite['taxa_reprovacao']:.2%} — possível regra ou "
                    "configuração inconsistente",
                    taxa_reprovacao,
                    limite["taxa_reprovacao"],
                )
            )
        return alertas
