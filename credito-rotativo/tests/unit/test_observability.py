"""Observabilidade: logs estruturados, correlation_id, ausência de PII e
alertas de métricas (erros/falhas, latência, reprovação)."""
from __future__ import annotations

import logging

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.infrastructure.config import Settings
from app.infrastructure.observability import FormatoEstruturado, Metricas
from app.infrastructure.persistence import RepositorioAvaliacoes


def _registros(caplog):
    return [r for r in caplog.records if r.name == "credito_rotativo"]


def _formatar(caplog) -> str:
    fmt = FormatoEstruturado()
    return "\n".join(fmt.format(r) for r in _registros(caplog))


def test_formato_estruturado(caplog):
    logger = logging.getLogger("credito_rotativo")
    logger.info("avaliacao_concluida", extra={"contexto": {"correlation_id": "abc"}})
    payload = [r for r in caplog.records if r.name == "credito_rotativo"]
    import json

    dados = json.loads(FormatoEstruturado().format(payload[0]))
    assert dados["evento"] == "avaliacao_concluida"
    assert dados["nivel"] == "INFO"
    assert dados["correlation_id"] == "abc"
    assert "timestamp" in dados


def test_log_concluida_com_correlation_id(cliente, settings, caplog):
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    with caplog.at_level(logging.INFO, logger="credito_rotativo"):
        usecase.executar(cliente(), "corr-1")
    concluidas = [r for r in _registros(caplog) if r.getMessage() == "avaliacao_concluida"]
    assert concluidas
    contexto = concluidas[0].contexto
    assert contexto["correlation_id"] == "corr-1"
    assert contexto["status"] == "aprovado"
    assert contexto["valor_liberado"] == "1000.00"


def test_log_sem_pii(cliente, settings, caplog):
    """LGPD: nome e CPF em claro nunca aparecem nos logs."""
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    with caplog.at_level(logging.INFO, logger="credito_rotativo"):
        usecase.executar(cliente(), "corr-lgpd")
    texto = _formatar(caplog)
    assert "Ana" not in texto
    assert "123.456" not in texto
    assert "hash-ana" in texto  # apenas o hash


def test_log_replay_idempotente(cliente, settings, caplog):
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    usecase.executar(cliente(), "corr-replay")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="credito_rotativo"):
        usecase.executar(cliente(), "corr-replay")
    eventos = [r.getMessage() for r in _registros(caplog)]
    assert "replay_idempotente" in eventos
    assert "avaliacao_concluida" not in eventos  # não reavaliou


def test_log_falha_em_erro(cliente, settings, caplog, monkeypatch):
    from app.domain.rules.perfil_gastos import PerfilGastosRule

    def _explodir(self, context):
        raise RuntimeError("boom")

    monkeypatch.setattr(PerfilGastosRule, "avaliar", _explodir)
    usecase = AvaliarCreditoUseCase(settings, RepositorioAvaliacoes())
    with caplog.at_level(logging.ERROR, logger="credito_rotativo"):
        try:
            usecase.executar(cliente(), "corr-falha")
        except RuntimeError:
            pass
    falhas = [r for r in _registros(caplog) if r.getMessage() == "avaliacao_falha"]
    assert falhas
    assert falhas[0].levelno == logging.ERROR
    assert falhas[0].contexto["correlation_id"] == "corr-falha"
    assert falhas[0].contexto["erro"] == "RuntimeError"
    # a falha também alimenta as métricas do /metricas
    assert usecase.metricas.falhas == 1
    assert usecase.metricas.ultimo_erro == "RuntimeError"
    assert usecase.metricas.snapshot()["falhas"] == 1


def test_falha_no_write_tambem_vira_metrica_e_alerta(cliente, settings, caplog):
    """Esgotado o retry do SQLite, a falha de persistência também é
    observável (NFR: "alertas para possíveis erros ou falhas")."""
    import pytest
    import sqlite3

    class RepositorioQuebrado(RepositorioAvaliacoes):
        def salvar(self, avaliacao):
            raise sqlite3.OperationalError("database is locked")

    usecase = AvaliarCreditoUseCase(settings, RepositorioQuebrado())
    with caplog.at_level(logging.ERROR, logger="credito_rotativo"):
        with pytest.raises(sqlite3.OperationalError):
            usecase.executar(cliente(), "corr-write")

    falhas = [r for r in _registros(caplog) if r.getMessage() == "avaliacao_falha"]
    assert falhas[0].levelno == logging.ERROR
    assert falhas[0].contexto["correlation_id"] == "corr-write"
    assert falhas[0].contexto["erro"] == "OperationalError"

    assert usecase.metricas.falhas == 1
    assert usecase.metricas.ultimo_erro == "OperationalError"
    assert usecase.metricas.snapshot()["taxa_erro"] == 1.0
    alertas = usecase.metricas.avaliar_alertas(usecase.metricas.snapshot())
    assert [a["codigo"] for a in alertas] == ["taxa_de_erro_acima_do_limite"]
    # nada foi persistido: o relatório continua vazio
    assert usecase.repositorio.listar() == []


# ---------- alertas (NFR: "alertas para possíveis erros ou falhas") ----------


def test_sem_dados_nao_alerta():
    metricas = Metricas()
    assert metricas.avaliar_alertas(metricas.snapshot()) == []


def test_alerta_latencia_p95_acima_do_slo():
    metricas = Metricas(limite_latencia_p95_ms=100.0)
    metricas.registrar_latencia(150.0)
    alertas = metricas.avaliar_alertas(metricas.snapshot())
    assert [a["codigo"] for a in alertas] == ["latencia_p95_acima_do_slo"]
    assert alertas[0]["severidade"] == "critico"
    assert alertas[0]["valor"] == 150.0
    assert alertas[0]["limite"] == 100.0
    assert "1s" in alertas[0]["mensagem"]


def test_latencia_exatamente_no_limite_nao_alerta():
    metricas = Metricas(limite_latencia_p95_ms=150.0)
    metricas.registrar_latencia(150.0)
    assert metricas.avaliar_alertas(metricas.snapshot()) == []


def test_alerta_taxa_de_erro_com_tipo_da_falha():
    metricas = Metricas(limite_taxa_erro=0.05)
    for _ in range(10):
        metricas.registrar(aprovado=True)
    metricas.registrar_falha("RuntimeError")

    snapshot = metricas.snapshot()
    assert snapshot["falhas"] == 1
    assert snapshot["ultimo_erro"] == "RuntimeError"
    assert snapshot["taxa_erro"] == 0.0909  # 1 falha em 11 processadas

    alertas = metricas.avaliar_alertas(snapshot)
    assert [a["codigo"] for a in alertas] == ["taxa_de_erro_acima_do_limite"]
    assert alertas[0]["severidade"] == "critico"
    assert "RuntimeError" in alertas[0]["mensagem"]


def test_alerta_reprovacao_anomala_e_warning():
    metricas = Metricas(limite_taxa_reprovacao=0.90)
    for _ in range(3):
        metricas.registrar(aprovado=False)
    alertas = metricas.avaliar_alertas(metricas.snapshot())
    assert [a["codigo"] for a in alertas] == ["taxa_de_reprovacao_anomala"]
    assert alertas[0]["severidade"] == "warning"
    assert alertas[0]["valor"] == 1.0


def test_todos_os_alertas_podem_disparar_juntos():
    metricas = Metricas(
        limite_latencia_p95_ms=100.0,
        limite_taxa_erro=0.05,
        limite_taxa_reprovacao=0.90,
    )
    metricas.registrar_latencia(900.0)
    metricas.registrar(aprovado=False)
    metricas.registrar_falha("RuntimeError")
    alertas = metricas.avaliar_alertas(metricas.snapshot())
    assert [a["codigo"] for a in alertas] == [
        "latencia_p95_acima_do_slo",
        "taxa_de_erro_acima_do_limite",
        "taxa_de_reprovacao_anomala",
    ]
    assert all(
        {"codigo", "severidade", "mensagem", "valor", "limite"} <= set(a)
        for a in alertas
    )


def test_alerta_so_loga_na_transicao(caplog):
    """Polling do /metricas não repete o mesmo evento (sem spam)."""
    metricas = Metricas(limite_taxa_erro=0.05)
    metricas.registrar_falha("RuntimeError")
    snapshot = metricas.snapshot()

    with caplog.at_level(logging.WARNING, logger="credito_rotativo"):
        metricas.avaliar_alertas(snapshot)
        metricas.avaliar_alertas(snapshot)

    disparos = [r for r in _registros(caplog) if r.getMessage() == "alerta_disparado"]
    assert len(disparos) == 1
    assert disparos[0].levelno == logging.WARNING
    assert disparos[0].contexto["codigo"] == "taxa_de_erro_acima_do_limite"
    assert disparos[0].contexto["valor"] == 1.0


def test_alerta_encerra_quando_a_metrica_normaliza(caplog):
    metricas = Metricas(limite_taxa_erro=0.05)
    metricas.registrar_falha("RuntimeError")
    metricas.avaliar_alertas(metricas.snapshot())
    caplog.clear()

    for _ in range(19):  # 1 falha em 20 = exatamente 5% → não é mais alerta
        metricas.registrar(aprovado=True)
    with caplog.at_level(logging.INFO, logger="credito_rotativo"):
        alertas = metricas.avaliar_alertas(metricas.snapshot())

    assert alertas == []
    eventos = [r.getMessage() for r in _registros(caplog)]
    assert "alerta_encerrado" in eventos
    assert "alerta_disparado" not in eventos


def test_limites_dos_alertas_vem_das_env_vars(monkeypatch):
    """`CREDITO_ALERTA_*` calibra os limites sem mudar código (12-factor)."""
    monkeypatch.setenv("CREDITO_ALERTA_LATENCIA_P95_MS", "50")
    monkeypatch.setenv("CREDITO_ALERTA_TAXA_ERRO_MAX", "0.0")
    usecase = AvaliarCreditoUseCase(Settings(), RepositorioAvaliacoes())
    usecase.metricas.registrar_latencia(80.0)
    usecase.metricas.registrar_falha("RuntimeError")

    alertas = usecase.metricas.avaliar_alertas(usecase.metricas.snapshot())
    assert [a["codigo"] for a in alertas] == [
        "latencia_p95_acima_do_slo",
        "taxa_de_erro_acima_do_limite",
    ]
