"""Testes da API (adapter HTTP)."""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


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


def test_validacao_rejeita_gastos_insuficientes():
    resp = client.post(
        "/avaliacoes",
        json=payload(gastos_ultimos_meses=["100.00"] * 3),
    )
    assert resp.status_code == 422


def test_saude():
    assert client.get("/saude").json() == {"status": "ok"}
