"""Fixtures compartilhadas: cliente válido padrão + settings padrão."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.models import CustomerProfile
from app.infrastructure.config import Settings

CAMINHO_DATASET = Path(__file__).resolve().parents[1] / "data" / "clientes_ficticios.json"


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


@pytest.fixture
def clientes_ficticios() -> list[dict]:
    """Dataset do RF1: a 'lista de clientes' do case, em JSON.

    Cada entrada é um payload válido de `POST /avaliacoes/batch`.
    """
    return json.loads(CAMINHO_DATASET.read_text(encoding="utf-8"))
