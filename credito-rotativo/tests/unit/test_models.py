"""Modelagem de dados: invariants e propriedades derivadas."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.models import CustomerProfile, Estado


def test_criacao_valida():
    c = CustomerProfile(
        nome="Ana",
        cpf_hash="h",
        score_credito=500,
        valor_fatura=Decimal("100"),
        limite_disponivel=Decimal("400"),
        atrasos_meses=0,
        gastos_ultimos_meses=[Decimal("100")] * 6,
    )
    assert c.limite_total == Decimal("500")
    assert c.utilizacao_limite == Decimal("0.2")


def test_rejeita_score_fora_do_intervalo():
    with pytest.raises(ValueError):
        CustomerProfile(
            nome="Ana", cpf_hash="h", score_credito=1001,
            valor_fatura=Decimal("0"), limite_disponivel=Decimal("0"),
            atrasos_meses=0, gastos_ultimos_meses=[Decimal("0")] * 6,
        )


def test_rejeita_meses_insuficientes():
    with pytest.raises(ValueError):
        CustomerProfile(
            nome="Ana", cpf_hash="h", score_credito=500,
            valor_fatura=Decimal("0"), limite_disponivel=Decimal("0"),
            atrasos_meses=0, gastos_ultimos_meses=[Decimal("0")] * 5,
        )


def test_rejeita_nome_vazio(cliente):
    with pytest.raises(ValueError):
        cliente(nome="   ")


def test_rejeita_valor_fatura_negativa(cliente):
    with pytest.raises(ValueError):
        cliente(valor_fatura=Decimal("-100"))


def test_rejeita_limite_negativo(cliente):
    with pytest.raises(ValueError):
        cliente(limite_disponivel=Decimal("-500"))


def test_rejeita_atrasos_negativos(cliente):
    with pytest.raises(ValueError):
        cliente(atrasos_meses=-1)


def test_rejeita_gastos_negativos(cliente):
    with pytest.raises(ValueError):
        cliente(gastos_ultimos_meses=[Decimal("1000.00")] * 5 + [Decimal("-50")])


def test_maquina_de_estados():
    assert Estado.RECEBIDO.pode_ir_para(Estado.EM_AVALIACAO)
    assert Estado.EM_AVALIACAO.pode_ir_para(Estado.AVALIADO)
    assert Estado.EM_AVALIACAO.pode_ir_para(Estado.FALHA)
    assert Estado.FALHA.pode_ir_para(Estado.EM_AVALIACAO)  # retry
    assert not Estado.AVALIADO.pode_ir_para(Estado.RECEBIDO)
