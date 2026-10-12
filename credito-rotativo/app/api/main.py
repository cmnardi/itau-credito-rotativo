"""Adapter HTTP (FastAPI).

Endpoints:
- POST /avaliacoes        — avalia um cliente
- POST /avaliacoes/batch  — avalia uma lista de clientes
- GET  /relatorio         — aprovados, reprovados e valores liberados
                           (JSON; com `Accept: text/csv` devolve o download em CSV)
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
from fastapi.responses import JSONResponse, Response

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.api.csv_export import negociar_formato, serializar_relatorio_csv
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


@app.get(
    "/relatorio",
    response_model=RelatorioResponse,
    summary="Relatório de avaliações (JSON ou CSV)",
    description=(
        "Aprovados, reprovados e valores liberados (RF5). Por padrão devolve "
        "JSON; enviando `Accept: text/csv` o mesmo recurso devolve o relatório "
        "em CSV (duas seções: RESUMO e DETALHES) pronto para download."
    ),
    responses={
        200: {
            "description": (
                "JSON por padrão; CSV quando o cliente pede `Accept: text/csv`."
            ),
            "content": {
                "text/csv": {
                    "schema": {"type": "string"},
                    "example": (
                        "RESUMO\n"
                        "gerado_em;2026-10-12T20:00:00+00:00\n"
                        "total_avaliacoes;1\n"
                        "aprovados;1\n"
                        "reprovados;0\n"
                        "valor_total_liberado;1000.00\n"
                        "taxa_aprovacao;1.0\n"
                        "\n"
                        "DETALHES\n"
                        "timestamp;status;valor_liberado;cpf_hash;motivos;"
                        "regras_aplicadas;idempotency_key\n"
                        "2026-10-12T20:00:00+00:00;aprovado;1000.00;"
                        "3b0f...;;ScoreMinimoRule | HistoricoAtrasosRule;a2d1...\n"
                    ),
                }
            },
        }
    },
)
def relatorio(
    accept: Annotated[
        str | None,
        Header(
            description=(
                "Content negotiation: envie `text/csv` para exportar o "
                "relatório em CSV (padrão: `application/json`)."
            )
        ),
    ] = None,
) -> RelatorioResponse | Response:
    rel = _usecase.relatorio()
    if negociar_formato(accept) == "csv":
        # Response direto: o FastAPI devolve como está, sem passar pelo
        # response_model — só o content-type muda; o conteúdo vem do mesmo
        # caso de uso que abastece o JSON.
        return Response(
            content=serializar_relatorio_csv(rel),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="relatorio_avaliacoes.csv"'
            },
        )
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
