"""Testes de performance: latência e vazão (NFR: ≤ 1s/avaliação, 10k/min)."""
from __future__ import annotations

import time
from decimal import Decimal

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.domain.models import CustomerProfile
from app.infrastructure.config import Settings
from app.infrastructure.persistence import RepositorioAvaliacoes


def _cliente(i: int) -> CustomerProfile:
    return CustomerProfile(
        nome=f"Cliente {i}",
        cpf_hash=f"hash-{i}",
        score_credito=700 + (i % 100),
        valor_fatura=Decimal("1000.00"),
        limite_disponivel=Decimal("4000.00"),
        atrasos_meses=i % 3,
        gastos_ultimos_meses=[Decimal("1000.00")] * 6,
    )


def test_latencia_por_avaliacao():
    """NFR: avaliação em até 1 segundo."""
    usecase = AvaliarCreditoUseCase(Settings(), RepositorioAvaliacoes())
    inicio = time.perf_counter()
    usecase.executar(_cliente(0), "perf-0")
    latencia_ms = (time.perf_counter() - inicio) * 1000
    assert latencia_ms < 1000
    print(f"\nlatência por avaliação: {latencia_ms:.2f} ms")


def test_vazao_meta_10k_min():
    """NFR: picos de até 10.000 avaliações/minuto (~167/s)."""
    usecase = AvaliarCreditoUseCase(Settings(), RepositorioAvaliacoes())
    n = 2000
    inicio = time.perf_counter()
    for i in range(n):
        usecase.executar(_cliente(i), f"perf-{i}")
    decorrido = time.perf_counter() - inicio
    vazao = n / decorrido
    print(f"\nvazão: {vazao:.0f} avaliações/s ({vazao * 60:.0f}/min)")
    assert vazao > 167
