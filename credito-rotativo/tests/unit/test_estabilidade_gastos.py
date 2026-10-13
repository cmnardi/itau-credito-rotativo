"""R4 — Estabilidade de gastos (scoring)."""
from __future__ import annotations

from decimal import Decimal

from app.domain.models import EvaluationContext
from app.domain.rules.estabilidade_gastos import EstabilidadeGastosRule


def regra():
    return EstabilidadeGastosRule(variacao_max=Decimal("0.30"), peso=10)


def test_gastos_estaveis(cliente):
    ctx = EvaluationContext(customer=cliente())
    assert ctx.customer.variacao_gastos == 0
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 10


def test_gastos_instaveis(cliente):
    # variação alta: dp populacional 400 / média 500 = 0.80 > 0.30
    gastos = [
        Decimal("100"), Decimal("900"), Decimal("100"), Decimal("900"),
        Decimal("100"), Decimal("900"),
    ]
    ctx = EvaluationContext(customer=cliente(gastos_ultimos_meses=gastos))
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 0
    assert any("variação" in m for m in ctx.motivos)


def test_todos_zero(cliente):
    ctx = EvaluationContext(
        customer=cliente(gastos_ultimos_meses=[Decimal("0")] * 6)
    )
    assert ctx.customer.variacao_gastos == 0
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 10
