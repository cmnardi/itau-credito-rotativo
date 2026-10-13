"""Configuração via variáveis de ambiente (padrão 12-factor).

Tipada, com defaults, validada no boot (fail fast).
Manutenção = trocar a env var, sem alterar código nem redeploy.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CREDITO_")

    # R1 — Score mínimo (bloqueio)
    score_minimo: int = 600
    # R2 — Histórico de atrasos (bloqueio)
    max_atrasos_meses: int = 2
    # R3 — Utilização do limite (scoring em banda)
    util_limite_min: Decimal = Decimal("0.10")
    util_limite_max: Decimal = Decimal("0.90")
    util_limite_peso: int = 10
    # R4 — Estabilidade de gastos (scoring)
    estabilidade_max: Decimal = Decimal("0.30")
    estabilidade_peso: int = 10
    # R5 — Perfil de gastos (scoring)
    perfil_gastos_fator: Decimal = Decimal("1.5")
    perfil_gastos_peso: int = 10
    # Decisão
    limite_aprovacao: int = 20  # máx 30 → aprova com 2 dos 3 critérios de scoring
    # Cálculo do valor máximo
    valor_fator_fatura: Decimal = Decimal("1.0")
    valor_pct_limite: Decimal = Decimal("0.50")
    valor_teto: Decimal = Decimal("10000.00")
    valor_ajuste_min: Decimal = Decimal("0.50")
    # Alertas (NFR: "alertas para possíveis erros ou falhas")
    alerta_latencia_p95_ms: float = 1000.0  # NFR de latência: ≤ 1s por avaliação
    alerta_taxa_erro_max: float = 0.05  # falhas acima de 5% do volume processado
    alerta_reprovacao_min: float = 0.90  # reprovação ≥ 90% → regra/config suspeita
    # Persistência: "memoria" (padrão) ou "sqlite" (arquivo)
    persistencia: Literal["memoria", "sqlite"] = "memoria"
    db_path: str = "avaliacoes.db"
    # LGPD: salt do hash de CPF (simulação — em produção usar KMS/vault)
    cpf_salt: str = "case-rotativo"

    def params(self, regra: str) -> dict:
        """Construtor kwargs da regra nomeada (usado pelo registry)."""
        return {
            "score_minimo": {"score_minimo": self.score_minimo},
            "historico_atrasos": {"max_atrasos_meses": self.max_atrasos_meses},
            "utilizacao_limite": {
                "uso_min": self.util_limite_min,
                "uso_max": self.util_limite_max,
                "peso": self.util_limite_peso,
            },
            "estabilidade_gastos": {
                "variacao_max": self.estabilidade_max,
                "peso": self.estabilidade_peso,
            },
            "perfil_gastos": {
                "fator": self.perfil_gastos_fator,
                "peso": self.perfil_gastos_peso,
            },
        }[regra]
