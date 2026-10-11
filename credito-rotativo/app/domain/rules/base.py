"""Chain of Responsibility — handler abstrato (template method).

A base cuida do encadeamento e do short-circuit; subclasses implementam
apenas `avaliar()`. Regras são stateless: a cadeia pode ser reutilizada
entre avaliações (o estado por request vive no EvaluationContext).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import EvaluationContext, Status


class AbstractRule(ABC):
    def __init__(self) -> None:
        self._next: "AbstractRule | None" = None

    def set_next(self, rule: "AbstractRule") -> "AbstractRule":
        self._next = rule
        return rule  # encadeamento fluido

    def handle(self, context: EvaluationContext) -> EvaluationContext:
        self.avaliar(context)
        if context.status is Status.REPROVADO:
            return context  # short-circuit automático
        return self._next.handle(context) if self._next else context

    @abstractmethod
    def avaliar(self, context: EvaluationContext) -> None: ...

    def _aplicada(self, context: EvaluationContext) -> None:
        context.regras_aplicadas.append(self.__class__.__name__)
