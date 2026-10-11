"""Registry de regras e montagem da cadeia.

Extensibilidade (Open/Closed): nova regra = nova classe concreta
registrada aqui — nenhuma alteração no motor nem nas regras existentes.
"""
from __future__ import annotations

from app.domain.rules.base import AbstractRule
from app.domain.rules.estabilidade_gastos import EstabilidadeGastosRule
from app.domain.rules.historico_atrasos import HistoricoAtrasosRule
from app.domain.rules.perfil_gastos import PerfilGastosRule
from app.domain.rules.score_minimo import ScoreMinimoRule
from app.domain.rules.utilizacao_limite import UtilizacaoLimiteRule
from app.infrastructure.config import Settings

REGISTRY: dict[str, type[AbstractRule]] = {
    "score_minimo": ScoreMinimoRule,
    "historico_atrasos": HistoricoAtrasosRule,
    "utilizacao_limite": UtilizacaoLimiteRule,
    "estabilidade_gastos": EstabilidadeGastosRule,
    "perfil_gastos": PerfilGastosRule,
}

# Ordem fixa: bloqueios primeiro (short-circuit barato), scoring depois.
ORDEM_PADRAO = [
    "score_minimo",
    "historico_atrasos",
    "utilizacao_limite",
    "estabilidade_gastos",
    "perfil_gastos",
]


def montar_cadeia(config: Settings) -> AbstractRule:
    raiz = REGISTRY[ORDEM_PADRAO[0]](**config.params(ORDEM_PADRAO[0]))
    atual = raiz
    for nome in ORDEM_PADRAO[1:]:
        atual = atual.set_next(REGISTRY[nome](**config.params(nome)))
    return raiz
