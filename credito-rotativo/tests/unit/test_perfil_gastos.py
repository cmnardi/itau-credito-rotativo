"""R5 — Perfil de gastos (scoring)."""
from __future__ import annotations

from decimal import Decimal

from app.domain.models import EvaluationContext
from app.domain.rules.perfil_gastos import PerfilGastosRule


def regra():
    return PerfilGastosRule(fator=Decimal("1.5"), peso=10)


def test_fatura_na_media(cliente):
    # fatura 1000 ≤ média 1000 × 1.5 = 1500
    ctx = EvaluationContext(customer=cliente())
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 10


def test_fatura_acima_do_historico(cliente):
    # fatura 2000 > média 1000 × 1.5 = 1500
    ctx = EvaluationContext(
        customer=cliente(valor_fatura=Decimal("2000.00"))
    )
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 0
    assert any("histórico" in m for m in ctx.motivos)
