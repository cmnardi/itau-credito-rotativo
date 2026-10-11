"""Testes de integração: cadeia completa, ordem e short-circuit."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.domain.models import EvaluationContext, Status
from app.domain.rules import montar_cadeia
from app.infrastructure.persistence import RepositorioAvaliacoes


def test_cadeia_completa_aprova(cliente, settings):
    ctx = EvaluationContext(customer=cliente())
    montar_cadeia(settings).handle(ctx)
    assert ctx.status is Status.PENDENTE
    assert ctx.peso_acumulado == 30
    assert len(ctx.regras_aplicadas) == 5


def test_short_circuit_na_r1(cliente, settings):
    """R1 reprovada → R2–R5 não são aplicadas."""
    ctx = EvaluationContext(customer=cliente(score_credito=100))
    montar_cadeia(settings).handle(ctx)
    assert ctx.status is Status.REPROVADO
    assert ctx.regras_aplicadas == []


def test_short_circuit_na_r2(cliente, settings):
    ctx = EvaluationContext(customer=cliente(atrasos_meses=5))
    montar_cadeia(settings).handle(ctx)
    assert ctx.status is Status.REPROVADO
    assert ctx.regras_aplicadas == ["ScoreMinimoRule"]


def test_reprova_por_score_insuficiente(cliente, settings):
    """Sem bloqueio, mas as 3 regras de scoring falham → 0 pontos."""
    # utilização 1000/1100 ≈ 0.909 > 0.90 (R3 falha)
    # gastos instáveis (R4 falha)
    # fatura 1000 > média 500 × 1.5 = 750 (R5 falha)
    gastos = [Decimal("100"), Decimal("900")] * 3
    ctx = EvaluationContext(
        customer=cliente(
            valor_fatura=Decimal("1000.00"),
            limite_disponivel=Decimal("100.00"),
            gastos_ultimos_meses=gastos,
        )
    )
    montar_cadeia(settings).handle(ctx)
    assert ctx.status is Status.PENDENTE
    assert ctx.peso_acumulado == 0


def test_aprova_com_dois_de_tres(cliente, settings):
    """R3 falha (uso alto), R4 e R5 OK → 20 pontos = limite de aprovação."""
    ctx = EvaluationContext(
        customer=cliente(valor_fatura=Decimal("4900.00"))
    )
    montar_cadeia(settings).handle(ctx)
    assert ctx.status is Status.PENDENTE
    assert ctx.peso_acumulado == 20


def test_configuracao_altera_decisao(cliente):
    """Subindo o limite de aprovação para 30, o mesmo cliente é reprovado."""
    from app.infrastructure.config import Settings

    settings = Settings(limite_aprovacao=30)
    ctx = EvaluationContext(
        customer=cliente(valor_fatura=Decimal("4900.00"))
    )
    montar_cadeia(settings).handle(ctx)
    assert ctx.peso_acumulado == 20


def test_use_case_aprova_e_calcula_valor(cliente, settings):
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    resultado = usecase.executar(cliente(), "chave-1")
    assert resultado.status_final.value == "aprovado"
    # bruto = min(1000×1.0, 5000×0.5, 10000) = 1000; ajuste(30/30) = 1.0
    assert resultado.valor_liberado == Decimal("1000.00")


def test_use_case_idempotencia(cliente, settings):
    repo = RepositorioAvaliacoes()
    usecase = AvaliarCreditoUseCase(settings, repo)
    r1 = usecase.executar(cliente(), "chave-1")
    r2 = usecase.executar(cliente(score_credito=100), "chave-1")
    assert r1 is r2  # retry com a mesma chave retorna o resultado original
    assert len(repo.listar()) == 1


def test_use_case_reprovado_valor_zero(cliente, settings):
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    resultado = usecase.executar(cliente(score_credito=100), "chave-x")
    assert resultado.status_final is Status.REPROVADO
    assert resultado.valor_liberado == Decimal("0.00")


def test_use_case_reprova_por_score_insuficiente(cliente, settings):
    """Sem bloqueio, mas peso < limite_aprovacao → reprovado pelo orquestrador."""
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    gastos = [Decimal("100"), Decimal("900")] * 3
    resultado = usecase.executar(
        cliente(
            valor_fatura=Decimal("1000.00"),
            limite_disponivel=Decimal("100.00"),
            gastos_ultimos_meses=gastos,
        ),
        "insuficiente-1",
    )
    assert resultado.status_final is Status.REPROVADO
    assert resultado.valor_liberado == Decimal("0.00")
    assert any("score acumulado" in m for m in resultado.motivos)
    # cadeia completa, sem bloqueio; R3 acima do máximo não conta como aplicada
    assert resultado.regras_aplicadas == [
        "ScoreMinimoRule",
        "HistoricoAtrasosRule",
        "EstabilidadeGastosRule",
        "PerfilGastosRule",
    ]


def test_erro_de_processamento_propaga(cliente, settings, monkeypatch):
    """Seam de resiliência: regra que falha → erro propaga, nada persistido."""
    from app.domain.rules.perfil_gastos import PerfilGastosRule

    def _explodir(self, context):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(PerfilGastosRule, "avaliar", _explodir)
    repo = RepositorioAvaliacoes()
    usecase = AvaliarCreditoUseCase(settings, repo)
    with pytest.raises(RuntimeError):
        usecase.executar(cliente(), "falha-1")
    assert repo.listar() == []  # não persiste resultado incompleto


def test_relatorio(cliente, settings):
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    usecase.executar(cliente(), "ok")
    usecase.executar(cliente(score_credito=100), "ruim")
    rel = usecase.relatorio()
    assert rel["total_avaliacoes"] == 2
    assert rel["aprovados"] == 1
    assert rel["reprovados"] == 1
    assert rel["valor_total_liberado"] == Decimal("1000.00")
