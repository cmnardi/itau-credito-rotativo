"""Schemas Pydantic do adapter (API). Validação de entrada acontece aqui;
o domínio recebe dados já validados.

Exemplos embutidos (`json_schema_extra` / `openapi_examples`) aparecem
no Swagger (`/docs`) — servem de documentação viva e de massa de teste.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

_EXEMPLO_APROVADO = {
    "nome": "Ana Silva",
    "cpf": "123.456.789-00",
    "score_credito": 750,
    "valor_fatura": "1000.00",
    "limite_disponivel": "4000.00",
    "atrasos_meses": 0,
    "gastos_ultimos_meses": [
        "1000.00", "1200.00", "900.00", "1100.00", "1000.00", "1000.00",
    ],
}

_EXEMPLO_REPROVADO_SCORE = {
    "nome": "Carlos Souza",
    "cpf": "987.654.321-00",
    "score_credito": 520,
    "valor_fatura": "500.00",
    "limite_disponivel": "4500.00",
    "atrasos_meses": 0,
    "gastos_ultimos_meses": ["500.00"] * 6,
}

_EXEMPLO_REPROVADO_ATRASOS = {
    "nome": "Maria Lima",
    "cpf": "111.222.333-44",
    "score_credito": 800,
    "valor_fatura": "800.00",
    "limite_disponivel": "4200.00",
    "atrasos_meses": 5,
    "gastos_ultimos_meses": ["800.00"] * 6,
}


class CustomerProfileRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [_EXEMPLO_APROVADO]}
    )

    nome: str = Field(min_length=1, examples=["Ana Silva"])
    cpf: str = Field(
        min_length=11,
        max_length=14,
        examples=["123.456.789-00"],
        description="CPF em qualquer formatação (não é persistido — só o hash)",
    )
    score_credito: int = Field(ge=0, le=1000, examples=[750])
    valor_fatura: Decimal = Field(ge=0, examples=["1000.00"])
    limite_disponivel: Decimal = Field(ge=0, examples=["4000.00"])
    atrasos_meses: int = Field(ge=0, examples=[0])
    gastos_ultimos_meses: list[Decimal] = Field(
        min_length=6, max_length=12, examples=[["1000.00"] * 6]
    )


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "aprovado",
                    "valor_liberado": "1000.00",
                    "motivos": [],
                    "regras_aplicadas": [
                        "ScoreMinimoRule",
                        "HistoricoAtrasosRule",
                        "UtilizacaoLimiteRule",
                        "EstabilidadeGastosRule",
                        "PerfilGastosRule",
                    ],
                    "idempotency_key": "a2d11401d9030a29e16fcfe24a72f42d5af63ca4f219ffa02976688503af758e",
                }
            ]
        }
    )

    status: str = Field(examples=["aprovado"])
    valor_liberado: Decimal = Field(examples=["1000.00"])
    motivos: list[str] = Field(examples=[[]])
    regras_aplicadas: list[str] = Field(
        examples=[["ScoreMinimoRule", "HistoricoAtrasosRule"]]
    )
    idempotency_key: str = Field(examples=["a2d11401d9030a29e16fcfe24a72f42d5af63ca4f219ffa02976688503af758e"])


class RelatorioResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total_avaliacoes": 3,
                    "aprovados": 1,
                    "reprovados": 2,
                    "valor_total_liberado": "1000.00",
                    "taxa_aprovacao": 0.3333,
                    "avaliacoes": [],
                }
            ]
        }
    )

    total_avaliacoes: int = Field(examples=[3])
    aprovados: int = Field(examples=[1])
    reprovados: int = Field(examples=[2])
    valor_total_liberado: Decimal = Field(examples=["1000.00"])
    taxa_aprovacao: float = Field(examples=[0.3333])
    avaliacoes: list[EvaluationResponse] = Field(examples=[[]])
