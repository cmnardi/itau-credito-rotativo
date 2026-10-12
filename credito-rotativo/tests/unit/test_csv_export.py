"""Testes da exportação do relatório em CSV (Epic 7, item 6)."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

import pytest

from app.api.csv_export import negociar_formato, serializar_relatorio_csv
from app.domain.models import CreditEvaluation, Status

COLUNAS = [
    "timestamp",
    "status",
    "valor_liberado",
    "cpf_hash",
    "motivos",
    "regras_aplicadas",
    "idempotency_key",
]


@pytest.mark.parametrize(
    "accept,esperado",
    [
        (None, "json"),
        ("", "json"),
        ("*/*", "json"),
        ("application/json", "json"),
        # browser: só quer HTML e curinga → JSON
        ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "json"),
        ("text/csv", "csv"),
        ("TEXT/CSV", "csv"),  # media type é case-insensitive
        ("text/*", "csv"),
        ("text/csv;q=0.9, application/json;q=0.8", "csv"),
        ("application/json;q=0.9, text/csv;q=0.8", "json"),
        ("text/csv;q=0.5, */*;q=0.8", "json"),  # q explícito x curinga
        ("text/csv;q=0, */*;q=1", "json"),  # q=0 = não aceito CSV
        ("text/csv, application/json", "json"),  # empate → JSON (compatível)
        ("text/csv;q=invalido", "csv"),  # q malformado não derruba a troca
    ],
)
def test_negociacao_pelo_header_accept(accept: str | None, esperado: str):
    assert negociar_formato(accept) == esperado


def avaliacao(**overrides) -> CreditEvaluation:
    dados: dict = {
        "cpf_hash": "hash-ana",
        "status_final": Status.APROVADO,
        "valor_liberado": Decimal("1000.00"),
        "motivos": [],
        "regras_aplicadas": ["ScoreMinimoRule", "UtilizacaoLimiteRule"],
        "idempotency_key": "chave-1",
    }
    dados.update(overrides)
    return CreditEvaluation(**dados)


def relatorio(avaliacoes: list[CreditEvaluation]) -> dict:
    aprovados = [a for a in avaliacoes if a.status_final is Status.APROVADO]
    return {
        "total_avaliacoes": len(avaliacoes),
        "aprovados": len(aprovados),
        "reprovados": len(avaliacoes) - len(aprovados),
        "valor_total_liberado": sum(
            (a.valor_liberado for a in avaliacoes), Decimal("0.00")
        ),
        "taxa_aprovacao": round(len(aprovados) / len(avaliacoes), 4)
        if avaliacoes
        else 0.0,
        "avaliacoes": avaliacoes,
    }


def secoes(texto: str) -> tuple[list[list[str]], list[list[str]]]:
    """Divide o CSV em (linhas do RESUMO, linhas do DETALHES), parseando com `;`."""
    resumo, detalhes = texto.split("\n\n")

    def ler(bloco: str) -> list[list[str]]:
        return list(csv.reader(io.StringIO(bloco), delimiter=";"))

    return ler(resumo), ler(detalhes)


def test_relatorio_vazio_ainda_exporta_resumo():
    resumo, detalhes = secoes(serializar_relatorio_csv(relatorio([])))
    assert resumo[0] == ["RESUMO"]
    assert ["total_avaliacoes", "0"] in resumo
    assert ["valor_total_liberado", "0.00"] in resumo
    assert detalhes[0] == ["DETALHES"]
    assert detalhes[1] == COLUNAS
    assert len(detalhes) == 2  # só o cabeçalho


def test_detalhes_uma_linha_por_avaliacao_com_cpf_hash():
    texto = serializar_relatorio_csv(
        relatorio(
            [
                avaliacao(),
                avaliacao(
                    cpf_hash="hash-carlos",
                    status_final=Status.REPROVADO,
                    valor_liberado=Decimal("0.00"),
                    motivos=["score 520 < 600"],
                    idempotency_key="chave-2",
                ),
            ]
        )
    )
    resumo, detalhes = secoes(texto)
    assert ["aprovados", "1"] in resumo
    assert ["reprovados", "1"] in resumo
    assert ["valor_total_liberado", "1000.00"] in resumo
    assert detalhes[1] == COLUNAS
    assert len(detalhes) == 4  # cabeçalho + 2 avaliações
    assert detalhes[2][1:4] == ["aprovado", "1000.00", "hash-ana"]
    assert detalhes[3][1:4] == ["reprovado", "0.00", "hash-carlos"]
    assert detalhes[3][4] == "score 520 < 600"
    assert "|" in detalhes[2][5]  # regras unidas por |


def test_campos_com_separador_sao_escapados_pelo_csv():
    texto = serializar_relatorio_csv(
        relatorio([avaliacao(motivos=["atrasos 5 > 2 meses; risco alto", "score; baixo"])])
    )
    _, detalhes = secoes(texto)
    assert detalhes[2][4] == "atrasos 5 > 2 meses; risco alto | score; baixo"


def test_resumo_inclui_gerado_em_iso8601():
    resumo, _ = secoes(serializar_relatorio_csv(relatorio([avaliacao()] * 3)))
    assert resumo[1][0] == "gerado_em"
    assert datetime.fromisoformat(resumo[1][1]).tzinfo is not None
    assert ["total_avaliacoes", "3"] in resumo
    assert ["valor_total_liberado", "3000.00"] in resumo
