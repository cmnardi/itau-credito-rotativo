"""Schemas Pydantic do adapter (API). Validação de entrada acontece aqui;
o domínio recebe dados já validados."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class CustomerProfileRequest(BaseModel):
    nome: str = Field(min_length=1)
    cpf: str = Field(min_length=11, max_length=14, description="CPF em qualquer formatação")
    score_credito: int = Field(ge=0, le=1000)
    valor_fatura: Decimal = Field(ge=0)
    limite_disponivel: Decimal = Field(ge=0)
    atrasos_meses: int = Field(ge=0)
    gastos_ultimos_meses: list[Decimal] = Field(min_length=6, max_length=12)


class EvaluationResponse(BaseModel):
    status: str
    valor_liberado: Decimal
    motivos: list[str]
    regras_aplicadas: list[str]
    idempotency_key: str


class RelatorioResponse(BaseModel):
    total_avaliacoes: int
    aprovados: int
    reprovados: int
    valor_total_liberado: Decimal
    taxa_aprovacao: float
    avaliacoes: list[EvaluationResponse]
