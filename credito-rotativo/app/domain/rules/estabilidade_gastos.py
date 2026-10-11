"""R4 — Estabilidade de gastos (scoring).

Coeficiente de variação (dp/média) dos gastos dos últimos meses:
variação alta = receita imprevisível = risco.
"""
from __future__ import annotations

from decimal import Decimal

from app.domain.models import EvaluationContext
from app.domain.rules.base import AbstractRule


class EstabilidadeGastosRule(AbstractRule):
    def __init__(self, variacao_max: Decimal, peso: int) -> None:
        super().__init__()
        self.variacao_max = variacao_max
        self.peso = peso

    def avaliar(self, context: EvaluationContext) -> None:
        variacao = context.customer.variacao_gastos
        if variacao <= self.variacao_max:
            context.peso_acumulado += self.peso
        else:
            context.motivos.append(
                f"variação de gastos {variacao:.2f} > máximo {self.variacao_max:.2f}"
            )
        self._aplicada(context)
