"""Persistência: memória vs SQLite (sobrevive a reinícios)."""
from __future__ import annotations

from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.infrastructure.config import Settings
from app.infrastructure.persistence import (
    RepositorioAvaliacoes,
    SqliteRepositorioAvaliacoes,
    construir_repositorio,
)


def test_fabrica_seleciona_persistencia():
    assert isinstance(construir_repositorio(Settings()), RepositorioAvaliacoes)
    assert isinstance(
        construir_repositorio(
            Settings(persistencia="sqlite", db_path=":memory:")
        ),
        SqliteRepositorioAvaliacoes,
    )


def test_sqlite_persiste_entre_instancias(cliente, tmp_path):
    """Simula reinício do serviço: os dados continuam no arquivo."""
    caminho = str(tmp_path / "avaliacoes.db")
    settings = Settings(persistencia="sqlite", db_path=caminho)

    usecase1 = AvaliarCreditoUseCase(
        settings, SqliteRepositorioAvaliacoes(caminho)
    )
    r1 = usecase1.executar(cliente(), "chave-1")
    assert r1.status_final.value == "aprovado"

    # nova instância (novo processo) lendo o mesmo arquivo
    usecase2 = AvaliarCreditoUseCase(
        settings, SqliteRepositorioAvaliacoes(caminho)
    )
    r2 = usecase2.executar(cliente(score_credito=100), "chave-1")
    # idempotência cruzada: retorna o resultado original, não reavalia
    assert r2.status_final.value == "aprovado"
    assert r2.valor_liberado == r1.valor_liberado
    assert len(usecase2.repositorio.listar()) == 1


def test_sqlite_relatorio(cliente, tmp_path):
    caminho = str(tmp_path / "avaliacoes.db")
    settings = Settings(persistencia="sqlite", db_path=caminho)
    usecase = AvaliarCreditoUseCase(
        settings, SqliteRepositorioAvaliacoes(caminho)
    )
    usecase.executar(cliente(), "ok")
    usecase.executar(cliente(score_credito=100), "ruim")
    rel = usecase.relatorio()
    assert rel["total_avaliacoes"] == 2
    assert rel["aprovados"] == 1
    assert rel["reprovados"] == 1
