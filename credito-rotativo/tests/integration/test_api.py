"""Testes da API (adapter HTTP)."""
from __future__ import annotations

import csv
import io
import logging
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import app
from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.infrastructure.config import Settings
from app.infrastructure.observability import Metricas
from app.infrastructure.persistence import RepositorioAvaliacoes

client = TestClient(app)

CODIGOS_ALERTA = {
    "latencia_p95_acima_do_slo",
    "taxa_de_erro_acima_do_limite",
    "taxa_de_reprovacao_anomala",
}


def payload(**overrides) -> dict:
    dados = {
        "nome": "Ana Silva",
        "cpf": "123.456.789-00",
        "score_credito": 750,
        "valor_fatura": "1000.00",
        "limite_disponivel": "4000.00",
        "atrasos_meses": 0,
        "gastos_ultimos_meses": ["1000.00"] * 6,
    }
    dados.update(overrides)
    return dados


def test_avaliacao_aprovada():
    resp = client.post("/avaliacoes", json=payload())
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "aprovado"
    assert corpo["valor_liberado"] == "1000.00"
    assert len(corpo["regras_aplicadas"]) == 5


def test_avaliacao_reprovada():
    resp = client.post(
        "/avaliacoes", json=payload(cpf="999.888.777-66", score_credito=100)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reprovado"
    assert resp.json()["valor_liberado"] == "0.00"


def test_idempotencia_por_cpf():
    r1 = client.post("/avaliacoes", json=payload())
    r2 = client.post("/avaliacoes", json=payload(score_credito=100))
    # mesmo CPF → mesma chave → mesmo resultado
    assert r1.json()["idempotency_key"] == r2.json()["idempotency_key"]
    assert r2.json()["status"] == "aprovado"


def test_idempotencia_por_header():
    r1 = client.post(
        "/avaliacoes", json=payload(), headers={"X-Idempotency-Key": "manual-1"}
    )
    r2 = client.post(
        "/avaliacoes",
        json=payload(cpf="111.222.333-44", score_credito=100),
        headers={"X-Idempotency-Key": "manual-1"},
    )
    assert r1.json() == r2.json()


def test_batch():
    resp = client.post(
        "/avaliacoes/batch",
        json=[payload(), payload(score_credito=100)],
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert [c["status"] for c in corpo] == ["aprovado", "aprovado"]  # mesmo CPF


def test_relatorio():
    client.post("/avaliacoes", json=payload(nome="Batch"))
    resp = client.get("/relatorio")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total_avaliacoes"] >= 1
    assert corpo["aprovados"] >= 1


def test_metricas():
    resp = client.get("/metricas")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_metricas_conta_replay_idempotente():
    """Reenvio com a mesma chave não reavalia, mas o request fica visível
    em `replays` — sem inflar `total` nem as taxas."""
    antes = client.get("/metricas").json()
    chave = "replay-metricas-1"
    r1 = client.post("/avaliacoes", json=payload(), headers={"X-Idempotency-Key": chave})
    r2 = client.post(
        "/avaliacoes",
        json=payload(cpf="999.888.777-66", score_credito=100),
        headers={"X-Idempotency-Key": chave},
    )
    assert r1.json() == r2.json()  # segundo veio do cache
    depois = client.get("/metricas").json()

    assert depois["total"] - antes["total"] == 1  # uma decisão nova
    assert depois["replays"] - antes["replays"] == 1  # um request em replay
    assert depois["falhas"] == antes["falhas"]


def test_metricas_expoe_alertas_e_status():
    """`/metricas` junta métricas + alertas avaliados + status agregado."""
    resp = client.get("/metricas")
    assert resp.status_code == 200
    corpo = resp.json()

    # sem erros de processamento nos testes que rodam via API
    assert corpo["falhas"] == 0
    assert corpo["taxa_erro"] == 0.0
    assert corpo["ultimo_erro"] is None
    assert isinstance(corpo["replays"], int)  # replay idempotente visível

    assert isinstance(corpo["alertas"], list)
    assert all(a["codigo"] in CODIGOS_ALERTA for a in corpo["alertas"])
    assert corpo["status"] == ("alerta" if corpo["alertas"] else "ok")


def test_falha_no_pipeline_vira_alerta_no_metricas(monkeypatch, caplog):
    """NFR: erro de processamento (estado FALHA) vira alerta observável."""
    from app.api import main as api
    from app.domain.rules.perfil_gastos import PerfilGastosRule

    # caso de uso isolado com limite de taxa de erro em 0 → qualquer falha alerta
    usecase_falho = AvaliarCreditoUseCase(
        Settings(),
        RepositorioAvaliacoes(),
        metricas=Metricas(limite_taxa_erro=0.0),
    )
    monkeypatch.setattr(api, "_usecase", usecase_falho)

    def _explodir(self, context):
        raise RuntimeError("boom")

    monkeypatch.setattr(PerfilGastosRule, "avaliar", _explodir)
    cliente = TestClient(api.app, raise_server_exceptions=False)
    assert cliente.post("/avaliacoes", json=payload(cpf="777.888.999-00")).status_code == 500

    with caplog.at_level(logging.WARNING, logger="credito_rotativo"):
        corpo = cliente.get("/metricas").json()

    assert corpo["falhas"] == 1
    assert corpo["ultimo_erro"] == "RuntimeError"
    assert corpo["taxa_erro"] == 1.0
    assert corpo["status"] == "alerta"
    assert [a["codigo"] for a in corpo["alertas"]] == ["taxa_de_erro_acima_do_limite"]
    eventos = [
        r.getMessage() for r in caplog.records if r.name == "credito_rotativo"
    ]
    assert "alerta_disparado" in eventos  # a transição também vira log


def test_validacao_rejeita_gastos_insuficientes():
    resp = client.post(
        "/avaliacoes",
        json=payload(gastos_ultimos_meses=["100.00"] * 3),
    )
    assert resp.status_code == 422


def test_erro_de_dominio_retorna_400():
    """Gasto negativo passa pelo schema Pydantic, mas o domínio rejeita (fail-fast)."""
    resp = client.post(
        "/avaliacoes",
        json=payload(
            cpf="444.555.666-77",
            gastos_ultimos_meses=[
                "1000.00", "-500.00", "900.00", "1100.00", "1000.00", "1000.00",
            ],
        ),
    )
    assert resp.status_code == 400
    assert "negativo" in resp.json()["detail"]


def test_saude():
    assert client.get("/saude").json() == {"status": "ok"}


def test_relatorio_csv_via_accept():
    """Content negotiation: `Accept: text/csv` baixa o relatório em CSV."""
    client.post("/avaliacoes", json=payload(cpf="555.444.333-22"))
    resp = client.get("/relatorio", headers={"Accept": "text/csv"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == (
        'attachment; filename="relatorio_avaliacoes.csv"'
    )

    corpo = resp.text
    assert corpo.startswith("RESUMO\n")
    assert "\n\nDETALHES\n" in corpo
    assert "cpf_hash" in corpo  # identifica sem expor CPF
    assert "123.456.789-00" not in corpo  # PII nunca sai

    linhas = list(csv.reader(io.StringIO(corpo), delimiter=";"))
    cabecalho = linhas[linhas.index(["DETALHES"]) + 1]
    assert cabecalho == [
        "timestamp",
        "status",
        "valor_liberado",
        "cpf_hash",
        "motivos",
        "regras_aplicadas",
        "idempotency_key",
    ]
    # pelo menos uma linha de dados, com hash de 64 chars e status conhecido
    dados = linhas[linhas.index(cabecalho) + 1 :]
    assert len(dados) >= 1
    assert dados[0][1] in {"aprovado", "reprovado"}
    assert len(dados[0][3]) == 64


def test_relatorio_padrao_continua_json():
    resp = client.get("/relatorio")
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["total_avaliacoes"] >= 1


def test_relatorio_negocia_q_values():
    """`text/csv` perde para `application/json` quando a qualidade é menor."""
    resp = client.get(
        "/relatorio",
        headers={"Accept": "application/json;q=0.9, text/csv;q=0.8"},
    )
    assert resp.headers["content-type"].startswith("application/json")

    csv_resp = client.get(
        "/relatorio", headers={"Accept": "text/csv;q=0.9, application/json;q=0.8"}
    )
    assert csv_resp.headers["content-type"].startswith("text/csv")


def test_swagger_documenta_csv():
    """O Swagger mostra o header Accept e o content-type text/csv."""
    spec = client.get("/openapi.json").json()
    operacao = spec["paths"]["/relatorio"]["get"]
    assert "text/csv" in operacao["responses"]["200"]["content"]
    assert "application/json" in operacao["responses"]["200"]["content"]
    assert any(p["name"] == "accept" for p in operacao["parameters"])
