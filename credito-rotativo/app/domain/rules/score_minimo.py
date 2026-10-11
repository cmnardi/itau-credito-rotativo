"""R1 — Score mínimo (bloqueio)."""
from __future__ import annotations

from app.domain.models import EvaluationContext, Status
from app.domain.rules.base import AbstractRule


class ScoreMinimoRule(AbstractRule):
    def __init__(self, score_minimo: int) -> None:
        super().__init__()
        self.score_minimo = score_minimo

    def avaliar(self, context: EvaluationContext) -> None:
        if context.customer.score_credito < self.score_minimo:
            context.status = Status.REPROVADO
            context.motivos.append(
                f"score {context.customer.score_credito} < mínimo {self.score_minimo}"
            )
        else:
            self._aplicada(context)
