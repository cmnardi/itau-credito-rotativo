"""R2 — Histórico de atrasos (bloqueio).

O threshold (`max_atrasos_meses`) vem da configuração: se a janela de
observação mudar, só a env var muda — o modelo permanece.
"""
from __future__ import annotations

from app.domain.models import EvaluationContext, Status
from app.domain.rules.base import AbstractRule


class HistoricoAtrasosRule(AbstractRule):
    def __init__(self, max_atrasos_meses: int) -> None:
        super().__init__()
        self.max_atrasos_meses = max_atrasos_meses

    def avaliar(self, context: EvaluationContext) -> None:
        if context.customer.atrasos_meses > self.max_atrasos_meses:
            context.status = Status.REPROVADO
            context.motivos.append(
                f"atrasos em {context.customer.atrasos_meses} mês(es) > máximo "
                f"{self.max_atrasos_meses}"
            )
        else:
            self._aplicada(context)
