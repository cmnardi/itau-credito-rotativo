# 3. Regras de Negócio e Configuração

## 3.1 Regras Propostas (com justificativa)

| # | Regra | Tipo | Critério | Peso | Justificativa |
|---|---|---|---|---|---|
| R1 | Score mínimo | Bloqueio | score ≥ `CREDITO_SCORE_MINIMO` (600) | — | Risco de inadimplência |
| R2 | Histórico de atrasos | Bloqueio | atrasos_meses ≤ `CREDITO_MAX_ATRASOS_MESES` (2) | — | Comportamento de pagamento |
| R3 | Utilização do limite | Scoring | `MIN` ≤ uso ≤ `MAX` (0.10–0.90) | 10 | Sinal de estresse financeiro |
| R4 | Estabilidade de gastos | Scoring | variação ≤ `CREDITO_ESTABILIDADE_MAX` (0.30) | 10 | Previsibilidade de receita |
| R5 | Perfil de gastos | Scoring | fatura ≤ média × `CREDITO_PERFIL_GASTOS_FATOR` (1.5) | 10 | Capacidade de pagamento |

## 3.2 Parametrização por variáveis de ambiente (padrão 12-factor)

| Variável | Padrão | Regra |
|---|---|---|
| `CREDITO_SCORE_MINIMO` | 600 | R1 |
| `CREDITO_MAX_ATRASOS_MESES` | 2 | R2 |
| `CREDITO_UTIL_LIMITE_MIN` | 0.10 | R3 |
| `CREDITO_UTIL_LIMITE_MAX` | 0.90 | R3 |
| `CREDITO_UTIL_LIMITE_PESO` | 10 | R3 |
| `CREDITO_ESTABILIDADE_MAX` | 0.30 | R4 |
| `CREDITO_ESTABILIDADE_PESO` | 10 | R4 |
| `CREDITO_PERFIL_GASTOS_FATOR` | 1.5 | R5 |
| `CREDITO_PERFIL_GASTOS_PESO` | 10 | R5 |
| `CREDITO_LIMITE_APROVACAO` | 20 | Decisão |

Carregadas via `pydantic-settings` (`infrastructure/config.py`): tipadas, com defaults, validadas no boot (fail fast). Manutenção = trocar a env, sem alterar código nem redeploy.

## 3.3 Modelo de scoring

- Cada regra de scoring contribui com seu **peso** ao `peso_acumulado` quando satisfeita
- Máximo = 30 (3 regras × 10); **`CREDITO_LIMITE_APROVACAO=20`** → aprova se ao menos 2 dos 3 critérios forem atendidos (sem bloqueio)
- **R3 em banda:** uso > MAX → 0 pts (estresse financeiro); uso < MIN → metade do peso (perfil inativo — pouco uso do cartão); dentro da banda → peso integral
- **R5 explicado:** compara a fatura atual com a média dos gastos dos últimos meses (`fatura ≤ média × FATOR`). Fatura coerente com o histórico = capacidade de pagamento previsível; fatura muito acima da média = pico de gastos = risco. O **"10" é o peso da regra** — os pontos que ela adiciona ao score quando satisfeita.

## 3.4 Design da Cadeia

`AbstractRule` — template method: a base cuida do encadeamento e do short-circuit; subclasses implementam apenas `avaliar()`:

```python
class AbstractRule(ABC):
    def __init__(self) -> None:
        self._next: "AbstractRule | None" = None

    def set_next(self, rule: "AbstractRule") -> "AbstractRule":
        self._next = rule
        return rule  # encadeamento fluido

    def handle(self, context: EvaluationContext) -> EvaluationContext:
        self.avaliar(context)
        if context.status is Status.REPROVADO:
            return context            # short-circuit automático
        return self._next.handle(context) if self._next else context

    @abstractmethod
    def avaliar(self, context: EvaluationContext) -> None: ...
```

Regra de bloqueio (R1):

```python
class ScoreMinimoRule(AbstractRule):
    def __init__(self, score_minimo: int):
        super().__init__()
        self.score_minimo = score_minimo

    def avaliar(self, context: EvaluationContext) -> None:
        if context.customer.score_credito < self.score_minimo:
            context.status = Status.REPROVADO
            context.motivos.append(f"score {context.customer.score_credito} < {self.score_minimo}")
        else:
            context.regras_aplicadas.append(self.__class__.__name__)
```

Regra de scoring (R5):

```python
class PerfilGastosRule(AbstractRule):
    def __init__(self, fator: Decimal, peso: int):
        super().__init__()
        self.fator = fator
        self.peso = peso

    def avaliar(self, context: EvaluationContext) -> None:
        media = sum(context.customer.gastos_ultimos_meses) / len(context.customer.gastos_ultimos_meses)
        if context.customer.valor_fatura <= media * self.fator:
            context.peso_acumulado += self.peso
        else:
            context.motivos.append("fatura acima do histórico de gastos")
        context.regras_aplicadas.append(self.__class__.__name__)
```

Registry + montagem da cadeia (ordem fixa, regras vindas das env vars):

```python
REGISTRY = {
    "score_minimo": ScoreMinimoRule,
    "historico_atrasos": HistoricoAtrasosRule,
    "utilizacao_limite": UtilizacaoLimiteRule,
    "estabilidade_gastos": EstabilidadeGastosRule,
    "perfil_gastos": PerfilGastosRule,
}

ORDEM_PADRAO = ["score_minimo", "historico_atrasos",
                "utilizacao_limite", "estabilidade_gastos", "perfil_gastos"]

def montar_cadeia(config: Settings) -> AbstractRule:
    raiz = REGISTRY[ORDEM_PADRAO[0]](**config.params(ORDEM_PADRAO[0]))
    atual = raiz
    for nome in ORDEM_PADRAO[1:]:
        atual = atual.set_next(REGISTRY[nome](**config.params(nome)))
    return raiz
```

Decisão final (no orquestrador): `aprovado = (status != REPROVADO) and (peso_acumulado >= limite_aprovacao)`.

## 3.5 Cálculo do Valor Máximo

```
bruto  = min(fatura × FATOR_FATURA, limite_total × PCT_LIMITE, TETO)
ajuste = AJUSTE_MIN + (1 − AJUSTE_MIN) × peso_acumulado / peso_maximo
valor  = bruto × ajuste   (quantizado em 0.01)
```

- **Premissa:** o rotativo não supera a fatura atual (`FATOR_FATURA=1.0`), nem uma fração do limite total (`PCT_LIMITE=0.50`), com teto absoluto (`TETO=10.000`)
- **Ajuste proporcional ao score:** quanto melhor o perfil (mais pesos acumulados), maior o valor dentro do teto; `AJUSTE_MIN=0.50` garante piso de 50% do bruto mesmo no limite mínimo de aprovação
- **peso_maximo** = soma dos pesos das regras de scoring (30 na configuração padrão)
- Tudo em `Decimal` (sem float money)

| Variável | Padrão |
|---|---|
| `CREDITO_VALOR_FATOR_FATURA` | 1.0 |
| `CREDITO_VALOR_PCT_LIMITE` | 0.50 |
| `CREDITO_VALOR_TETO` | 10000.00 |
| `CREDITO_VALOR_AJUSTE_MIN` | 0.50 |

## 3.6 Extensibilidade

Nova regra = nova classe concreta de handler, registrada na configuração da cadeia. Nenhuma alteração no motor nem nas regras existentes (Open/Closed).

## 3.7 Persistência e Retry (NFR de resiliência)

`CREDITO_PERSISTENCIA` escolhe a implementação (`memoria` = padrão; `sqlite` = arquivo em `CREDITO_DB_PATH`, sobrevive a reinício). O **write do SQLite** é protegido por retry com backoff exponencial, cobrindo indisponibilidade temporária (banco travado por outro processo, I/O transitório):

```
espera(n) = min(BACKOFF_MS × 2^(n−1), BACKOFF_MAX_MS)    para n = 1 … TENTATIVAS−1
```

- Só `sqlite3.OperationalError` é tratado como transitório — qualquer outro erro propaga na 1ª tentativa (retry não mascara bug)
- A abertura da conexão/schema segue a mesma política (boot com lock de outro processo)
- Cada tentativa loga `persistencia_retry` (WARNING) e a exaustão `persistencia_falha` (ERROR) — alimenta a taxa de erro/alertas do `/metricas`
- O lock do repositório fica tomado durante a espera: escritas não se intercalam na mesma conexão

| Variável | Padrão |
|---|---|
| `CREDITO_PERSISTENCIA` | `memoria` (`sqlite` para arquivo) |
| `CREDITO_DB_PATH` | `avaliacoes.db` |
| `CREDITO_PERSISTENCIA_RETRY_TENTATIVAS` | 3 |
| `CREDITO_PERSISTENCIA_RETRY_BACKOFF_MS` | 100 |
| `CREDITO_PERSISTENCIA_RETRY_BACKOFF_MAX_MS` | 2000 |
