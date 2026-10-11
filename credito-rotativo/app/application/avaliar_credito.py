"""Caso de uso — orquestrador da avaliação.

Fluxo: valida → monta cadeia (config) → executa → decide → calcula valor →
persiste. Isolado do adapter e das regras: substituível por workflow engine
(Temporal/Step Functions) sem mudar o domínio (seam para SAGA futuro).
"""
from __future__ import annotations

import time
from decimal import Decimal, ROUND_HALF_UP

from app.domain.models import (
    CreditEvaluation,
    CustomerProfile,
    Estado,
    EvaluationContext,
    Status,
)
from app.domain.rules import montar_cadeia
from app.infrastructure.config import Settings
from app.infrastructure.observability import Metricas
from app.infrastructure.persistence import RepositorioAvaliacoes

_CENTAVOS = Decimal("0.01")


class AvaliarCreditoUseCase:
    def __init__(
        self,
        config: Settings,
        repositorio: RepositorioAvaliacoes,
        metricas: Metricas | None = None,
    ) -> None:
        self.config = config
        self.repositorio = repositorio
        self.metricas = metricas if metricas is not None else Metricas()
        # Regras são stateless: a cadeia é construída uma vez e reutilizada
        # (cache de regras — meta de latência ≤ 1s por avaliação).
        self._cadeia = montar_cadeia(config)

    def executar(self, customer: CustomerProfile, idempotency_key: str) -> CreditEvaluation:
        # Idempotência: retry com a mesma chave retorna o resultado original.
        if (existente := self.repositorio.buscar_por_chave(idempotency_key)) is not None:
            return existente

        contexto = EvaluationContext(customer=customer)
        inicio = time.perf_counter()
        try:
            self._cadeia.handle(contexto)
        except Exception:
            # Seam de resiliência: estado FALHA permite retomada após retry.
            contexto.motivos.append("erro de processamento")
            raise
        finally:
            if self.metricas is not None:
                self.metricas.registrar_latencia((time.perf_counter() - inicio) * 1000)

        aprovado = (
            contexto.status is not Status.REPROVADO
            and contexto.peso_acumulado >= self.config.limite_aprovacao
        )
        if aprovado:
            contexto.status = Status.APROVADO
        elif contexto.status is not Status.REPROVADO:
            contexto.status = Status.REPROVADO
            contexto.motivos.append(
                f"score acumulado {contexto.peso_acumulado} < "
                f"limite de aprovação {self.config.limite_aprovacao}"
            )

        valor = (
            self._calcular_valor(customer, contexto.peso_acumulado)
            if aprovado
            else Decimal("0.00")
        )

        avaliacao = CreditEvaluation(
            cpf_hash=customer.cpf_hash,
            status_final=contexto.status,
            valor_liberado=valor,
            motivos=contexto.motivos,
            regras_aplicadas=contexto.regras_aplicadas,
            idempotency_key=idempotency_key,
        )
        self.repositorio.salvar(avaliacao)
        if self.metricas is not None:
            self.metricas.registrar(aprovado)
        return avaliacao

    def _calcular_valor(self, customer: CustomerProfile, peso_acumulado: int) -> Decimal:
        """valor = min(fatura × FATOR, limite_total × PCT, TETO) × ajuste(score)."""
        bruto = min(
            customer.valor_fatura * self.config.valor_fator_fatura,
            customer.limite_total * self.config.valor_pct_limite,
            self.config.valor_teto,
        )
        peso_maximo = (
            self.config.util_limite_peso
            + self.config.estabilidade_peso
            + self.config.perfil_gastos_peso
        )
        fracao = Decimal(peso_acumulado) / Decimal(peso_maximo)
        ajuste = self.config.valor_ajuste_min + (Decimal("1") - self.config.valor_ajuste_min) * fracao
        return (bruto * ajuste).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)

    def relatorio(self) -> dict:
        """RF5: aprovados, reprovados e respectivos valores liberados."""
        avaliacoes = self.repositorio.listar()
        aprovados = [a for a in avaliacoes if a.status_final is Status.APROVADO]
        reprovados = [a for a in avaliacoes if a.status_final is Status.REPROVADO]
        total = len(avaliacoes)
        return {
            "total_avaliacoes": total,
            "aprovados": len(aprovados),
            "reprovados": len(reprovados),
            "valor_total_liberado": sum((a.valor_liberado for a in aprovados), Decimal("0.00")),
            "taxa_aprovacao": round(len(aprovados) / total, 4) if total else 0.0,
            "avaliacoes": avaliacoes,
        }
