"""Exportação do relatório em CSV — content negotiation pelo header `Accept`.

O mesmo recurso (`GET /relatorio`) atende JSON (padrão) ou CSV: o cliente
requisita o formato com `Accept: text/csv` (RFC 7231). Nada de duplicar
endpoint — só o content-type muda.

Formato do CSV (separador `;`, abre direto no Excel pt-BR):

    RESUMO
    gerado_em;2026-10-12T20:00:00+00:00
    total_avaliacoes;3
    ...
    DETALHES
    timestamp;status;valor_liberado;cpf_hash;motivos;regras_aplicadas;idempotency_key

Duas seções: RESUMO (agregados do RF5, sempre presente — inclusive no
relatório vazio) e DETALHES (uma linha por avaliação). Leitura programática:
`pd.read_csv(caminho, sep=";")` ou `csv.reader(f, delimiter=";")`.

LGPD: o CPF não aparece — só o `cpf_hash` (SHA-256 + salt) que o adapter
já persiste; campos de lista são unidos por `|` e o `csv` quote o resto.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Literal

FORMATO_JSON = "json"
FORMATO_CSV = "csv"

TIPO_CSV = "text/csv"
TIPO_JSON = "application/json"

_COLUNAS = (
    "timestamp",
    "status",
    "valor_liberado",
    "cpf_hash",
    "motivos",
    "regras_aplicadas",
    "idempotency_key",
)

_CHAVES_RESUMO = (
    "total_avaliacoes",
    "aprovados",
    "reprovados",
    "valor_total_liberado",
    "taxa_aprovacao",
)


def negociar_formato(accept: str | None) -> Literal["csv", "json"]:
    """Escolhe o formato a partir do header `Accept` (q-values da RFC 7231).

    Sem header ou empate → JSON (compatível com browser, curl e clientes
    antigos que mandam `*/*`); CSV só quando for melhor pontuado.
    """
    if not accept:
        return FORMATO_JSON
    if _qualidade(accept, TIPO_CSV) > _qualidade(accept, TIPO_JSON):
        return FORMATO_CSV
    return FORMATO_JSON


def _qualidade(header: str, tipo: str) -> float:
    """Qualidade (q) atribuída a `tipo` no `Accept`.

    Ausência do tipo vale o curinga correspondente (`text/*` ou `*/*`);
    sem nenhuma menção, 0.0 — quem pede um formato explicitamente vence
    quem só mandou curinga.
    """
    genero = tipo.split("/", 1)[0]
    explicito: float | None = None
    q_genero = q_tudo = 0.0
    for parte in header.split(","):
        alvo, *params = (item.strip().lower() for item in parte.split(";"))
        q = 1.0
        for param in params:
            if param.startswith("q="):
                # q malformado é ignorado (RFC 7231): fica o default 1.0.
                try:
                    q = min(max(float(param[2:]), 0.0), 1.0)
                except ValueError:
                    q = 1.0
        if alvo == tipo:
            explicito = max(explicito or 0.0, q)
        elif alvo == f"{genero}/*":
            q_genero = max(q_genero, q)
        elif alvo == "*/*":
            q_tudo = max(q_tudo, q)
    if explicito is not None:
        return explicito
    return max(q_genero, q_tudo)


def serializar_relatorio_csv(relatorio: dict) -> str:
    """Renderiza o relatório (saída do caso de uso) como CSV de duas seções."""
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\n")

    escritor.writerow(["RESUMO"])
    escritor.writerow(["gerado_em", datetime.now(timezone.utc).isoformat(timespec="seconds")])
    for chave in _CHAVES_RESUMO:
        escritor.writerow([chave, relatorio[chave]])
    escritor.writerow([])
    escritor.writerow(["DETALHES"])
    escritor.writerow(_COLUNAS)
    for a in relatorio["avaliacoes"]:
        escritor.writerow(
            [
                a.timestamp.isoformat(),
                a.status_final.value,
                str(a.valor_liberado),
                a.cpf_hash,
                " | ".join(a.motivos),
                " | ".join(a.regras_aplicadas),
                a.idempotency_key,
            ]
        )
    return buffer.getvalue()
