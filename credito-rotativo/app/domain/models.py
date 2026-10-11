"""Modelos de domínio do sistema de crédito rotativo.

Domínio puro: sem dependências de framework. Validação fail-fast em
`__post_init__` garante os invariants no ponto de criação.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from statistics import pstdev


class Status(Enum):
    """Resultado de uma avaliação de crédito."""

    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REPROVADO = "reprovado"


class Estado(Enum):
    """Máquina de estados da avaliação (seam preparado para SAGA futuro)."""

    RECEBIDO = "recebido"
    EM_AVALIACAO = "em_avaliacao"
    AVALIADO = "avaliado"
    FALHA = "falha"

    def pode_ir_para(self, destino: "Estado") -> bool:
        return destino in _TRANSICOES[self]


# Definido fora do corpo da classe (a classe ainda não existe durante a definição).
_TRANSICOES: dict[Estado, set[Estado]] = {
    Estado.RECEBIDO: {Estado.EM_AVALIACAO},
    Estado.EM_AVALIACAO: {Estado.AVALIADO, Estado.FALHA},
    Estado.FALHA: {Estado.EM_AVALIACAO},  # retry idempotente
    Estado.AVALIADO: set(),
}


@dataclass(frozen=True)
class CustomerProfile:
    """Perfil do cliente (dados fictícios). O CPF já chega hasheado pelo adapter."""

    nome: str
    cpf_hash: str
    score_credito: int  # 0–1000
    valor_fatura: Decimal  # >= 0
    limite_disponivel: Decimal  # >= 0
    atrasos_meses: int  # >= 0 (janela/threshold definidos na R2 via config)
    gastos_ultimos_meses: list[Decimal]  # 6–12 meses, >= 0

    def __post_init__(self) -> None:
        if not self.nome.strip():
            raise ValueError("nome não pode ser vazio")
        if not 0 <= self.score_credito <= 1000:
            raise ValueError(f"score_credito fora do intervalo 0–1000: {self.score_credito}")
        if self.valor_fatura < 0:
            raise ValueError("valor_fatura não pode ser negativo")
        if self.limite_disponivel < 0:
            raise ValueError("limite_disponivel não pode ser negativo")
        if self.atrasos_meses < 0:
            raise ValueError("atrasos_meses não pode ser negativo")
        if not 6 <= len(self.gastos_ultimos_meses) <= 12:
            raise ValueError("gastos_ultimos_meses deve conter 6–12 meses")
        if any(g < 0 for g in self.gastos_ultimos_meses):
            raise ValueError("gastos_ultimos_meses não pode conter valores negativos")

    @property
    def limite_total(self) -> Decimal:
        """Premissa: fatura = saldo atual do cartão."""
        return self.valor_fatura + self.limite_disponivel

    @property
    def utilizacao_limite(self) -> Decimal:
        """Insumo da R3."""
        total = self.limite_total
        return Decimal("0") if total == 0 else self.valor_fatura / total

    @property
    def variacao_gastos(self) -> Decimal:
        """Coeficiente de variação (dp/média) — insumo da R4."""
        media = sum(self.gastos_ultimos_meses) / len(self.gastos_ultimos_meses)
        if media == 0:
            return Decimal("0")
        return Decimal(str(pstdev(self.gastos_ultimos_meses))) / media


@dataclass
class EvaluationContext:
    """Percorre a cadeia; regras de scoring acumulam peso aqui."""

    customer: CustomerProfile
    status: Status = Status.PENDENTE
    peso_acumulado: int = 0
    motivos: list[str] = field(default_factory=list)
    regras_aplicadas: list[str] = field(default_factory=list)


@dataclass
class CreditEvaluation:
    """Saída da avaliação (auditoria / persistência)."""

    cpf_hash: str
    status_final: Status
    valor_liberado: Decimal
    motivos: list[str]
    regras_aplicadas: list[str]
    idempotency_key: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    estado: Estado = Estado.AVALIADO
