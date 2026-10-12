"""Dataset fictício (RF1) — `data/clientes_ficticios.json`.

O case pede simular a avaliação "para uma lista de clientes": o dataset é
essa lista, no formato exato de `POST /avaliacoes/batch` (cobrindo bordas e
caminhos das 5 regras) e usado aqui de ponta a ponta — schema → API →
cadeia → relatório (RF5) → exportação CSV.
"""
from __future__ import annotations

import re
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.csv_export import serializar_relatorio_csv
from app.api.main import app
from app.api.schemas import CustomerProfileRequest
from app.application.avaliar_credito import AvaliarCreditoUseCase
from app.domain.models import CustomerProfile
from app.infrastructure.config import Settings
from app.infrastructure.persistence import RepositorioAvaliacoes

client = TestClient(app)

CAMPOS_RF1 = {
    "nome",
    "cpf",
    "score_credito",
    "valor_fatura",
    "limite_disponivel",
    "atrasos_meses",
    "gastos_ultimos_meses",
}

# nome → (status, valor_liberado) esperados, com o cenário que cada cliente cobre.
ESPERADO: dict[str, tuple[str, str]] = {
    "Ana Silva": ("aprovado", "1000.00"),         # perfil ideal: 30/30 pontos
    "Bruno Costa": ("reprovado", "0.00"),         # R1: score 520 < 600
    "Carla Dias": ("reprovado", "0.00"),          # R2: 5 atrasos > 2
    "Diego Ferraz": ("aprovado", "4166.67"),      # R3 falha (uso 95%) → 20/30 = aprova
    "Eduarda Lima": ("reprovado", "0.00"),        # 0/3: uso 96%, gastos instáveis, pico
    "Felipe Rocha": ("aprovado", "183.33"),       # perfil inativo (uso 4%) → 5+10+10 = 25
    "Gabriela Souza": ("aprovado", "1500.00"),    # borda R1: score 600 (mínimo aceito)
    "Henrique Alves": ("reprovado", "0.00"),      # borda R1: score 599
    "Isabela Mendes": ("aprovado", "1200.00"),    # borda R2: 2 atrasos é o máximo
    "João Pereira": ("reprovado", "0.00"),        # borda R2: 3 atrasos
    "Larissa Prado": ("aprovado", "2500.00"),     # R5 falha (fatura 2× a média) → 20/30
    "Marcos Oliveira": ("aprovado", "833.33"),    # R4 falha (variação 0.55) → 20/30
    "Natália Barbosa": ("aprovado", "10000.00"),  # perfil ideal com teto de 10.000
    "Otávio Ferreira": ("aprovado", "500.00"),    # borda R3: uso exatamente 90% + teto 50% do limite
}


def test_dataset_e_uma_lista_valida(clientes_ficticios: list[dict]):
    """RF1: campos do case, payload aceito pelo schema da API, CPFs únicos."""
    assert len(clientes_ficticios) >= 10
    cpfs: set[str] = set()
    for entrada in clientes_ficticios:
        assert set(entrada) == CAMPOS_RF1
        requisicao = CustomerProfileRequest.model_validate(entrada)  # 422 se inválido
        cpf = re.sub(r"\D", "", requisicao.cpf)
        assert len(cpf) == 11
        assert cpf not in cpfs, f"CPF repetido: {entrada['nome']}"
        cpfs.add(cpf)


def test_dataset_e_a_tabela_de_expectativas_estao_em_sincronia(clientes_ficticios: list[dict]):
    nomes = {entrada["nome"] for entrada in clientes_ficticios}
    assert nomes == set(ESPERADO)


def test_avaliacao_em_lote_reproduz_o_esperado(clientes_ficticios: list[dict]):
    """Ponta a ponta: o dataset entra pelo batch e sai com status/valor corretos."""
    resp = client.post("/avaliacoes/batch", json=clientes_ficticios)
    assert resp.status_code == 200
    respostas = resp.json()
    assert len(respostas) == len(clientes_ficticios) == len(ESPERADO)

    for entrada, resposta in zip(clientes_ficticios, respostas):
        status, valor = ESPERADO[entrada["nome"]]
        assert resposta["status"] == status, entrada["nome"]
        assert resposta["valor_liberado"] == valor, entrada["nome"]
        # reprovado sempre explica o porquê (motivo da rejeição)
        if status == "reprovado":
            assert resposta["motivos"], entrada["nome"]


def _para_dominio(entrada: dict, i: int) -> CustomerProfile:
    """Espelha o adapter: o domínio recebe o perfil já validado (hash no adapter)."""
    return CustomerProfile(
        nome=entrada["nome"],
        cpf_hash=f"hash-dataset-{i}",  # o hash real com salt é papel do adapter
        score_credito=entrada["score_credito"],
        valor_fatura=Decimal(entrada["valor_fatura"]),
        limite_disponivel=Decimal(entrada["limite_disponivel"]),
        atrasos_meses=entrada["atrasos_meses"],
        gastos_ultimos_meses=[Decimal(g) for g in entrada["gastos_ultimos_meses"]],
    )


def _avaliar_dataset(clientes_ficticios: list[dict]) -> AvaliarCreditoUseCase:
    """Caso de uso isolado: relatório só do dataset (o da API acumula outros testes)."""
    usecase = AvaliarCreditoUseCase(Settings(), RepositorioAvaliacoes())
    for i, entrada in enumerate(clientes_ficticios):
        usecase.executar(_para_dominio(entrada, i), f"dataset-{i}")
    return usecase


def test_relatorio_da_lista_rf5(clientes_ficticios: list[dict]):
    """RF5: aprovados, reprovados e valores liberados somados do dataset."""
    relatorio = _avaliar_dataset(clientes_ficticios).relatorio()
    aprovados = [v for s, v in ESPERADO.values() if s == "aprovado"]

    assert relatorio["total_avaliacoes"] == len(clientes_ficticios)
    assert relatorio["aprovados"] == len(aprovados)
    assert relatorio["reprovados"] == len(clientes_ficticios) - len(aprovados)
    assert relatorio["valor_total_liberado"] == sum(
        (Decimal(v) for v in aprovados), Decimal("0.00")
    )
    assert relatorio["taxa_aprovacao"] == round(len(aprovados) / len(ESPERADO), 4)


def test_relatorio_da_lista_vira_csv_usavel(clientes_ficticios: list[dict]):
    """A lista exporta em CSV com uma linha de detalhe por cliente."""
    relatorio = _avaliar_dataset(clientes_ficticios).relatorio()
    linhas = serializar_relatorio_csv(relatorio).split("\n")

    inicio_detalhes = linhas.index("DETALHES")
    cabecalho = linhas[inicio_detalhes + 1].split(";")
    dados = [linha for linha in linhas[inicio_detalhes + 2 :] if linha]
    assert cabecalho[0:3] == ["timestamp", "status", "valor_liberado"]
    assert len(dados) == len(clientes_ficticios)
    assert sum(1 for linha in dados if linha.split(";")[1] == "aprovado") == len(
        [v for s, v in ESPERADO.values() if s == "aprovado"]
    )
