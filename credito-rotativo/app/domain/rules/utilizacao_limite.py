"""R3 — Utilização do limite (scoring em banda).

- uso dentro de [MIN, MAX] → peso integral (perfil saudável)
- uso > MAX → 0 pontos (estresse financeiro)
- uso < MIN → metade do peso (perfil inativo — pouco uso do cartão)
"""
from __future__ import annotations

from decimal import Decimal

from app.domain.models import EvaluationContext
from app.domain.rules.base import AbstractRule


class UtilizacaoLimiteRule(AbstractRule):
    def __init__(self, uso_min: Decimal, uso_max: Decimal, peso: int) -> None:
        super().__init__()
        self.uso_min = uso_min
        self.uso_max = uso_max
        self.peso = peso

    def avaliar(self, context: EvaluationContext) -> None:
        uso = context.customer.utilizacao_limite
        if uso > self.uso_max:
            context.motivos.append(
                f"utilização {uso:.2%} do limite acima do máximo {self.uso_max:.2%}"
            )
        elif uso < self.uso_min:
            context.peso_acumulado += self.peso // 2  # perfil inativo: metade do peso
            context.motivos.append(
                f"utilização {uso:.2%} abaixo do mínimo {self.uso_min:.2%} (perfil inativo)"
            )
            self._aplicada(context)
        else:
            context.peso_acumulado += self.peso
            self._aplicada(context)
