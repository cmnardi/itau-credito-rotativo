"""R2 — Histórico de atrasos (bloqueio)."""
from __future__ import annotations

from app.domain.models import EvaluationContext, Status
from app.domain.rules.historico_atrasos import HistoricoAtrasosRule


def test_aprova_no_limite(cliente):
    ctx = EvaluationContext(customer=cliente(atrasos_meses=2))
    HistoricoAtrasosRule(max_atrasos_meses=2).avaliar(ctx)
    assert ctx.status is Status.PENDENTE


def test_reprova_acima_do_limite(cliente):
    ctx = EvaluationContext(customer=cliente(atrasos_meses=3))
    HistoricoAtrasosRule(max_atrasos_meses=2).avaliar(ctx)
    assert ctx.status is Status.REPROVADO
    assert any("atrasos" in m for m in ctx.motivos)
