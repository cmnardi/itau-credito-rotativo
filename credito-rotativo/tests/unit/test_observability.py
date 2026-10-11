"""Observabilidade: logs estruturados, correlation_id e ausência de PII."""
from __future__ import annotations

import logging

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.infrastructure.config import Settings
from app.infrastructure.observability import FormatoEstruturado
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
