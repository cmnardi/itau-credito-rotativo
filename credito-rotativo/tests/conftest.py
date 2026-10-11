"""Fixtures compartilhadas: cliente válido padrão + settings padrão."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.models import CustomerProfile
from app.infrastructure.config import Settings


@pytest.fixture
def cliente():
    """Cliente válido: score 750, utilização 20%, gastos estáveis, fatura na média."""

    def _cliente(**overrides) -> CustomerProfile:
        dados: dict = {
            "nome": "Ana Silva",
            "cpf_hash": "hash-ana",
            "score_credito": 750,
            "valor_fatura": Decimal("1000.00"),
            "limite_disponivel": Decimal("4000.00"),
            "atrasos_meses": 0,
            "gastos_ultimos_meses": [Decimal("1000.00")] * 6,
        }
        dados.update(overrides)
        return CustomerProfile(**dados)

    return _cliente


@pytest.fixture
def settings() -> Settings:
    return Settings()
