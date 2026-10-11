"""R3 — Utilização do limite (scoring em banda)."""
from __future__ import annotations

from decimal import Decimal

from app.domain.models import EvaluationContext
from app.domain.rules.utilizacao_limite import UtilizacaoLimiteRule


def regra():
    return UtilizacaoLimiteRule(
        uso_min=Decimal("0.10"), uso_max=Decimal("0.90"), peso=10
    )


def test_dentro_da_banda_peso_integral(cliente):
    # fatura 1000 / limite_total 5000 = 0.20
    ctx = EvaluationContext(customer=cliente())
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 10


def test_acima_do_maximo_zero_pontos(cliente):
    # fatura 1000 / limite_total 1100 ≈ 0.909 > 0.90
    ctx = EvaluationContext(
        customer=cliente(
            valor_fatura=Decimal("1000.00"), limite_disponivel=Decimal("100.00")
        )
    )
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 0
    assert any("utilização" in m for m in ctx.motivos)


def test_abaixo_do_minimo_meio_peso(cliente):
    # fatura 50 / limite_total 4050 ≈ 0.012 < 0.10
    ctx = EvaluationContext(
        customer=cliente(
            valor_fatura=Decimal("50.00"), limite_disponivel=Decimal("4000.00")
        )
    )
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 5


def test_limite_zerado(cliente):
    # fatura 0 e limite 0 → utilização 0 → perfil inativo (meio peso)
    ctx = EvaluationContext(
        customer=cliente(
            valor_fatura=Decimal("0"), limite_disponivel=Decimal("0")
        )
    )
    assert ctx.customer.utilizacao_limite == 0
    regra().avaliar(ctx)
    assert ctx.peso_acumulado == 5
