"""R1 — Score mínimo (bloqueio)."""
from __future__ import annotations

from app.domain.models import EvaluationContext, Status
from app.domain.rules.score_minimo import ScoreMinimoRule


def test_aprova_no_limite(cliente):
    ctx = EvaluationContext(customer=cliente(score_credito=600))
    ScoreMinimoRule(score_minimo=600).avaliar(ctx)
    assert ctx.status is Status.PENDENTE
    assert ctx.regras_aplicadas == ["ScoreMinimoRule"]


def test_reprova_abaixo_do_limite(cliente):
    ctx = EvaluationContext(customer=cliente(score_credito=599))
    ScoreMinimoRule(score_minimo=600).avaliar(ctx)
    assert ctx.status is Status.REPROVADO
    assert any("score" in m for m in ctx.motivos)
    assert ctx.regras_aplicadas == []
