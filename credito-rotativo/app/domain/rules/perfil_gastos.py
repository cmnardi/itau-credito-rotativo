"""R5 — Perfil de gastos (scoring).

Compara a fatura atual com a média dos gastos dos últimos meses
(`fatura <= média × FATOR`): fatura coerente com o histórico = capacidade
de pagamento previsível; fatura muito acima da média = pico de gastos = risco.
"""
from __future__ import annotations

from decimal import Decimal

from app.domain.models import EvaluationContext
from app.domain.rules.base import AbstractRule


class PerfilGastosRule(AbstractRule):
    def __init__(self, fator: Decimal, peso: int) -> None:
        super().__init__()
        self.fator = fator
        self.peso = peso

    def avaliar(self, context: EvaluationContext) -> None:
        media = context.customer.media_gastos
        if context.customer.valor_fatura <= media * self.fator:
            context.peso_acumulado += self.peso
        else:
            context.motivos.append(
                f"fatura {context.customer.valor_fatura} acima do histórico "
                f"(média {media:.2f} × fator {self.fator})"
            )
        self._aplicada(context)
