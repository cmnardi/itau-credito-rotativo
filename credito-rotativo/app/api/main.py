"""Adapter HTTP (FastAPI).

Endpoints:
- POST /avaliacoes        — avalia um cliente
- POST /avaliacoes/batch  — avalia uma lista de clientes
- GET  /relatorio         — aprovados, reprovados e valores liberados
- GET  /metricas          — volume, taxa de aprovação, latência p50/p95
- GET  /saude             — healthcheck
- GET  /docs              — Swagger (OpenAPI) com exemplos de request/response

LGPD: o CPF nunca é persistido — o adapter faz hash (SHA-256 + salt) antes
de entrar no domínio, e os logs/métricas não contêm PII.
"""
from __future__ import annotations

import hashlib
import re
from typing import Annotated

from fastapi import Body, FastAPI, Header
from fastapi.responses import JSONResponse

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.api.schemas import (
    CustomerProfileRequest,
    EvaluationResponse,
    RelatorioResponse,
    _EXEMPLO_APROVADO,
    _EXEMPLO_REPROVADO_ATRASOS,
    _EXEMPLO_REPROVADO_SCORE,
)
from app.domain.models import CreditEvaluation, CustomerProfile
from app.infrastructure.config import Settings
from app.infrastructure.observability import configurar_logging
from app.infrastructure.persistence import construir_repositorio

app = FastAPI(title="Crédito Rotativo — Case Itaú", version="1.0.0")

configurar_logging()  # logs estruturados (JSON) no stdout do container
_settings = Settings()
_usecase = AvaliarCreditoUseCase(_settings, construir_repositorio(_settings))


def _hash_cpf(cpf: str, salt: str) -> str:
    cpf_limpo = re.sub(r"\D", "", cpf)
    return hashlib.sha256(f"{salt}:{cpf_limpo}".encode()).hexdigest()


@app.exception_handler(ValueError)
def _erro_validacao(request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _para_dominio(req: CustomerProfileRequest) -> CustomerProfile:
    return CustomerProfile(
        nome=req.nome,
        cpf_hash=_hash_cpf(req.cpf, _usecase.config.cpf_salt),
        score_credito=req.score_credito,
        valor_fatura=req.valor_fatura,
        limite_disponivel=req.limite_disponivel,
        atrasos_meses=req.atrasos_meses,
        gastos_ultimos_meses=list(req.gastos_ultimos_meses),
    )


def _para_response(avaliacao: CreditEvaluation) -> EvaluationResponse:
    return EvaluationResponse(
        status=avaliacao.status_final.value,
        valor_liberado=avaliacao.valor_liberado,
        motivos=avaliacao.motivos,
        regras_aplicadas=avaliacao.regras_aplicadas,
        idempotency_key=avaliacao.idempotency_key,
    )


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok"}


@app.post("/avaliacoes", response_model=EvaluationResponse)
def avaliar(
    req: Annotated[
        CustomerProfileRequest,
        Body(
            openapi_examples={
                "cliente_aprovado": {
                    "summary": "Cliente aprovado (score alto, perfil estável)",
                    "value": _EXEMPLO_APROVADO,
                },
                "reprovado_por_score": {
                    "summary": "Reprovado pela R1 (score < 600)",
                    "value": _EXEMPLO_REPROVADO_SCORE,
                },
                "reprovado_por_atrasos": {
                    "summary": "Reprovado pela R2 (atrasos > 2 meses)",
                    "value": _EXEMPLO_REPROVADO_ATRASOS,
                },
            }
        ),
    ],
    x_idempotency_key: str | None = Header(default=None),
) -> EvaluationResponse:
    customer = _para_dominio(req)
    # Chave padrão: hash do CPF — a mesma submissão não reavalia o cliente.
    chave = x_idempotency_key or hashlib.sha256(customer.cpf_hash.encode()).hexdigest()
    return _para_response(_usecase.executar(customer, chave))


@app.post("/avaliacoes/batch", response_model=list[EvaluationResponse])
def avaliar_batch(
    reqs: Annotated[
        list[CustomerProfileRequest],
        Body(
            openapi_examples={
                "varios_clientes": {
                    "summary": "Lista com cliente aprovado e reprovado",
                    "value": [_EXEMPLO_APROVADO, _EXEMPLO_REPROVADO_SCORE],
                }
            }
        ),
    ],
) -> list[EvaluationResponse]:
    respostas = []
    for i, req in enumerate(reqs):
        customer = _para_dominio(req)
        chave = hashlib.sha256(customer.cpf_hash.encode()).hexdigest()
        respostas.append(_para_response(_usecase.executar(customer, chave)))
    return respostas


@app.get("/relatorio", response_model=RelatorioResponse)
def relatorio() -> RelatorioResponse:
    rel = _usecase.relatorio()
    return RelatorioResponse(
        total_avaliacoes=rel["total_avaliacoes"],
        aprovados=rel["aprovados"],
        reprovados=rel["reprovados"],
        valor_total_liberado=rel["valor_total_liberado"],
        taxa_aprovacao=rel["taxa_aprovacao"],
        avaliacoes=[_para_response(a) for a in rel["avaliacoes"]],
    )


@app.get("/metricas")
def metricas() -> dict:
    return _usecase.metricas.snapshot()
