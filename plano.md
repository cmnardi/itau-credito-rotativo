# Plano de Implementação — Sistema de Regras para Crédito Rotativo em Cartão de Crédito

**Case:** Processo Seletivo — Engenharia de Software Backend (Itaú)
**Prazo:** 7 dias corridos
**Stack:** Python 3.12 + FastAPI (API) + Pytest (testes) — escolhida por clareza, velocidade de desenvolvimento e ecossistema de testes; justificativa e trade-offs vs Java/Kotlin na seção de trade-offs
**Padrão central:** Chain of Responsibility (Strategy avaliado na implementação, se necessário)

---

## 1. Contexto

O cartão de crédito possui uma modalidade de crédito rotativo liberada automaticamente para clientes com perfil aprovado. A liberação depende de regras complexas baseadas em histórico de crédito, perfil de gastos e comportamento recente. A solução deve simular a avaliação e liberação para uma lista de clientes.

## 2. Diagramas

Fluxo da cadeia:

```mermaid
graph LR
  A[Entrada de dados] --> B[Validação]
  B --> C[R1 Score mínimo]
  C -- reprovado --> Z[Reprovado]
  C --> D[R2 Atrasos]
  D -- reprovado --> Z
  D --> E[R3 Utilização do limite]
  E --> F[R4 Estabilidade de gastos]
  F --> G[R5 Perfil de gastos]
  G --> H[Cálculo do valor]
  H --> I[Persistência + Relatório]
```

Sequência:

```mermaid
sequenceDiagram
  participant C as Cliente/API
  participant U as Caso de Uso
  participant R as Rule Chain
  participant P as Persistência
  C->>U: submete perfil
  U->>R: executa cadeia
  R-->>U: resultado parcial
  U->>U: calcula valor máximo
  U->>P: salva avaliação
  U-->>C: aprovação/reprovação + valor
```

Máquina de estados (preparação para SAGA):

```mermaid
stateDiagram-v2
  [*] --> RECEBIDO
  RECEBIDO --> EM_AVALIACAO: inicia cadeia
  EM_AVALIACAO --> AVALIADO: cadeia concluída
  EM_AVALIACAO --> FALHA: erro de processamento
  FALHA --> EM_AVALIACAO: retry (idempotente)
  AVALIADO --> [*]
```

Componentes:

```mermaid
graph TB
  subgraph Adapter
    API[API / CLI]
  end
  subgraph Application
    UC[Caso de Uso - Orquestrador]
  end
  subgraph Domain
    RC[Rule Chain - CoR]
    R1[R1 Score]
    R2[R2 Atrasos]
    R3[R3 Utilização]
    R4[R4 Estabilidade]
    R5[R5 Perfil de gastos]
    RC --> R1 --> R2 --> R3 --> R4 --> R5
  end
  subgraph Infrastructure
    P[Persistência]
    M[Métricas/Logs]
  end
  API --> UC --> RC
  UC --> P
  UC --> M
```

## 3. Modelo de Domínio e Estrutura do Projeto

### 3.1 Modelos (dataclasses / Pydantic)

`CustomerProfile` (domínio — dataclass frozen, `app/domain/models.py`):

```python
@dataclass(frozen=True)
class CustomerProfile:
    nome: str
    cpf_hash: str                        # SHA-256 + salt (LGPD) — hash feito no adapter
    score_credito: int                   # 0–1000
    valor_fatura: Decimal                # >= 0
    limite_disponivel: Decimal           # >= 0
    atrasos_meses: int                 # >= 0 (qtd. de meses com atraso, 0..n)
    gastos_ultimos_meses: list[Decimal]  # 6–12 meses, >= 0

    # __post_init__: validações fail-fast (nome, score 0–1000, valores >= 0, 6–12 meses de gastos)

    @property
    def limite_total(self) -> Decimal:   # premissa: fatura = saldo atual do cartão
        return self.valor_fatura + self.limite_disponivel

    @property
    def utilizacao_limite(self) -> Decimal:   # insumo da R3
        total = self.limite_total
        return Decimal("0") if total == 0 else self.valor_fatura / total

    @property
    def variacao_gastos(self) -> Decimal:     # coef. de variação (dp/média) — insumo da R4
        media = sum(self.gastos_ultimos_meses) / len(self.gastos_ultimos_meses)
        if media == 0:
            return Decimal("0")
        return Decimal(str(pstdev(self.gastos_ultimos_meses))) / media
```

Decisões: dataclass frozen (domínio puro, sem framework); `Decimal` para valores; Pydantic apenas no adapter da API; validação fail-fast; propriedades derivadas para R3/R4. **`atrasos_meses` é genérico (0..n): a janela/threshold é definida na regra R2 via configuração — se a regra mudar de 12 para outro número, só o config muda, o modelo permanece.**

`EvaluationContext` (percorre a cadeia — regras o mutam diretamente; o `RuleResult` do rascunho inicial foi simplificado nessa versão):
- customer: CustomerProfile
- status: Pendente | Aprovado | Reprovado
- peso_acumulado: int (soma dos pesos das regras de scoring satisfeitas)
- motivos: list[str]
- regras_aplicadas: list[str]

`CreditEvaluation` (saída/auditoria):
- cpf_hash, estado (RECEBIDO | EM_AVALIACAO | AVALIADO), status_final, valor_liberado: Decimal, motivos, regras_aplicadas, idempotency_key, timestamp

### 3.2 Estrutura de Pastas (Ports & Adapters)

```
credito-rotativo/
├── app/
│   ├── api/                           # Adapter (FastAPI)
│   │   ├── main.py                    # POST /avaliacoes, POST /avaliacoes/batch, GET /relatorio
│   │   └── schemas.py                 # Pydantic (request/response)
│   ├── application/                   # Caso de uso
│   │   └── avaliar_credito.py         # orquestrador: valida → monta cadeia (config) → executa → calcula valor → persiste
│   ├── domain/
│   │   ├── models.py                  # CustomerProfile, EvaluationContext, RuleResult, CreditEvaluation
│   │   └── rules/                     # Chain of Responsibility
│   │       ├── base.py                # AbstractRule: setNext()/handle()
│   │       ├── score_minimo.py        # R1 (bloqueio)
│   │       ├── historico_atrasos.py   # R2 (bloqueio)
│   │       ├── utilizacao_limite.py   # R3 (scoring)
│   │       ├── estabilidade_gastos.py # R4 (scoring)
│   │       └── perfil_gastos.py       # R5 (scoring)
│   └── infrastructure/
│       ├── config.py                  # Settings via env vars (pydantic-settings)
│       ├── persistence.py             # repositório em memória (SQLite opcional)
│       └── observability.py           # logs estruturados + métricas
├── tests/
│   ├── unit/                          # um por elo
│   └── integration/                   # cadeia completa
├── requirements.txt
└── README.md
```

Dependências apontam para dentro: `api → application → domain ← infrastructure` (domínio não depende de camadas externas).

## 4. Requisitos Funcionais

- **RF1:** Receber dados fictícios de clientes (nome, CPF, score de crédito, valor da fatura atual, limite disponível, nº de atrasos, comportamento de gastos nos últimos meses)
- **RF2:** Avaliar regras que definem se o crédito rotativo pode ser liberado
- **RF3:** Calcular o valor máximo de crédito rotativo para cada cliente elegível
- **RF4:** Permitir inclusão de novas regras sem alterar a estrutura principal (Chain of Responsibility)
- **RF5:** Gerar relatório com aprovados, reprovados e respectivos valores liberados
- **RF6:** Documentar critérios de decisão e justificar as regras aplicadas

## 5. Requisitos Não Funcionais

| NFR | Meta |
|---|---|
| Latência de decisão | ≤ 1s por avaliação |
| Escalabilidade | Picos de até 10.000 avaliações/min |
| Precisão/consistência | Sem liberações indevidas ou bloqueios incorretos |
| Extensibilidade | Novas regras sem refatoração do código base |
| Segurança/LGPD | Criptografia, controle de acesso, autenticação/autorização |
| Observabilidade | Métricas, logs estruturados, alertas |
| Resiliência | Continuidade e integridade em falhas temporárias |

## 6. Arquitetura

Camadas (Ports & Adapters):

```
API/Adapter → Caso de Uso (orquestrador) → Cadeia de Regras → Persistência
```

**Chain of Responsibility** — handler abstrato:

```
AbstractRule:
  - next: Rule
  - setNext(rule): Rule
  - handle(context: EvaluationContext): RuleResult

ConcreteRuleN:
  - handle(context):
      resultado = avaliar(context.customer)
      se bloqueador e reprovado → retorna reprovação (short-circuit)
      senão → acumula peso no context e repassa ao next
```

- **Short-circuit:** regras bloqueadoras (score mínimo, atrasos) reprovam imediatamente
- **Scoring:** regras de perfil acumulam pesos/pontos no `EvaluationContext`
- **Onde Strategy entraria:** se regras futuras exigirem algoritmos de cálculo intercambiáveis (fórmulas distintas de valor), o Strategy isola esses algoritmos — decisão adiada para a implementação

### 6.1 Evolução para SAGA (preparação)

**Decisão de escopo (ponto de apresentação):**
- **No case (teste):** Chain of Responsibility + orquestrador — a implementação mais comum e enxuta para uma avaliação read-only
- **Em produção real:** SAGA orquestrado (Temporal/Camunda/Step Functions) quando a liberação cruzar serviços transacionais (reserva de limite, contrato, notificação), com ações de compensação por passo
- **Por quê:** SAGA prematuro adiciona consistência eventual e complexidade de compensação sem benefício para um fluxo sem side effects; 2PC/XA é evitado em escala por fragilidade

**Por que não SAGA na v1:** SAGA coordena transações distribuídas com ações de compensação. O fluxo atual é uma avaliação read-only (regras puras + persistência do resultado) — não há efeitos colaterais a compensar, então CoR + orquestrador basta.

**Quando SAGA faz sentido:** o fluxo passar a ter side effects transacionais em múltiplos serviços (liberar limite, gerar contrato, notificar) — aí cada passo precisa de compensação. A avaliação vira o **primeiro step** do Saga futuro.

**Seams preparados na v1 (sem over-engineering):**
1. **Orquestrador isolado** (use case) — substituível por workflow engine (Temporal/Step Functions) sem mudar as regras
2. **Máquina de estados** da avaliação (RECEBIDO → EM_AVALIACAO → AVALIADO/FALHA) persistida — permite retomada após falha
3. **Eventos de domínio** (`AvaliacaoIniciada`, `RegraAvaliada`, `AvaliacaoConcluida`) — habilitam coreografia futura
4. **Idempotency key** na submissão — retries seguros em escala
5. **Regras como funções puras** — podem virar serviços remotos sem mudar o contrato

## 7. Regras de Negócio Propostas (com justificativa)

| # | Regra | Tipo | Critério | Peso | Justificativa |
|---|---|---|---|---|---|
| R1 | Score mínimo | Bloqueio | score ≥ `CREDITO_SCORE_MINIMO` (600) | — | Risco de inadimplência |
| R2 | Histórico de atrasos | Bloqueio | atrasos_meses ≤ `CREDITO_MAX_ATRASOS_MESES` (2) | — | Comportamento de pagamento |
| R3 | Utilização do limite | Scoring | `MIN` ≤ uso ≤ `MAX` (0.10–0.90) | 10 | Sinal de estresse financeiro |
| R4 | Estabilidade de gastos | Scoring | variação ≤ `CREDITO_ESTABILIDADE_MAX` (0.30) | 10 | Previsibilidade de receita |
| R5 | Perfil de gastos | Scoring | fatura ≤ média × `CREDITO_PERFIL_GASTOS_FATOR` (1.5) | 10 | Capacidade de pagamento |

**Parametrização por variáveis de ambiente (padrão 12-factor):**

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

**Modelo de scoring:**
- Cada regra de scoring contribui com seu **peso** ao `peso_acumulado` quando satisfeita
- Máximo = 30 (3 regras × 10); **`CREDITO_LIMITE_APROVACAO=20`** → aprova se ao menos 2 dos 3 critérios forem atendidos (sem bloqueio)
- **R3 em banda:** uso > MAX → 0 pts (estresse financeiro); uso < MIN → metade do peso (perfil inativo — pouco uso do cartão); dentro da banda → peso integral
- **R5 explicado:** compara a fatura atual com a média dos gastos dos últimos meses (`fatura ≤ média × FATOR`). Fatura coerente com o histórico = capacidade de pagamento previsível; fatura muito acima da média = pico de gastos = risco. O **"10" é o peso da regra** — os pontos que ela adiciona ao score quando satisfeita.

### 7.1 Design da Cadeia (Epic 2)

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

## 8. Cálculo do Valor Máximo

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

## 9. NFRs Detalhados

- **Latência:** regras O(1), cache de regras, processamento em memória
- **Escalabilidade:** serviço stateless, fila + workers (simulados), batch
- **Segurança/LGPD:** hash com salt no CPF, criptografia de campos sensíveis, RBAC simulado, logs sem PII
- **Observabilidade:** logs estruturados (corr. ID), métricas (volume, taxa aprovação/reprovação, latência p50/p95), alertas
- **Resiliência:** retries com backoff, circuit breaker, idempotência na submissão

## 10. Extensibilidade

Nova regra = nova classe concreta de handler, registrada na configuração da cadeia. Nenhuma alteração no motor nem nas regras existentes (Open/Closed).

## 11. Estratégia de Testes

- **Unitários:** cada elo isolado (aprovado/reprovado/limite)
- **Integração:** cadeia completa, ordem e short-circuit
- **Edge cases:** score no limite, atrasos no limite, limite zerado, dados ausentes
- **Performance:** medição de latência e vazão (meta: 10k/min)

## 12. Trade-offs

- **Python + FastAPI vs Java/Kotlin:** Python maximiza clareza e velocidade (prazo de 7 dias), deixando tempo para testes, docs e NFRs; Java/Kotlin seria mais alinhado à stack do Itaú, mas mais verboso para o escopo do case
- **CoR puro vs Strategy:** CoR atende ao fluxo sequencial de avaliação; Strategy só se justifica com múltiplos algoritmos de cálculo — decisão adiada
- **CoR + orquestrador vs SAGA na v1:** SAGA só se justifica com side effects transacionais distribuídos; a v1 prepara os seams (estados, eventos, idempotência) para a migração sem refatoração
- **Short-circuit vs avaliação completa:** reprovação imediata economiza processamento, mas perde diagnóstico completo (mitigado com log dos motivos até o ponto de corte)
- **Env vars vs código/YAML:** env vars são o padrão 12-factor (trocáveis por ambiente, sem redeploy); exigem tipagem e defaults (pydantic-settings)

## 13. Limitações e Evoluções

- Sem integrações reais (mocks aceitos pelo case)
- Versão inicial single-node; evoluir para fila/workers reais
- Evoluções: Strategy para cálculo, regras com ML, dashboard operacional

## 14. Entregáveis

- [ ] Documentação arquitetural (este documento)
- [ ] Diagramas (Mermaid)
- [ ] Estratégia de testes
- [ ] Justificativa de decisões e trade-offs
- [ ] Limitações e evoluções
- [ ] README com instruções (na implementação)

## 15. Declaração de Uso de IA

O uso de IA é liberado pelo case e deve ser explicitado. Registrar: uso na estruturação deste plano, exploração de padrões (CoR/Strategy) e redação da documentação — o raciocínio técnico, regras e trade-offs são do autor.

## 16. Backlog

**Epic 1 — Fundação**
- [x] Definir linguagem/stack (Python 3.12 + FastAPI + Pytest)
- [x] Estruturar camadas (adapter → use case → cadeia → persistence)
- [x] Modelar CustomerProfile e EvaluationContext

**Epic 2 — Cadeia de Regras**
- [x] Implementar AbstractRule (template method: set_next/handle + short-circuit)
- [x] Implementar R1 e R2 (bloqueio)
- [x] Implementar R3, R4, R5 (scoring com pesos)
- [x] Settings via env vars (pydantic-settings) + registry de regras

**Epic 3 — Cálculo e Relatório**
- [x] Calcular valor máximo com ajuste por score
- [x] Gerar relatório de aprovados/reprovados e valores

**Epic 4 — NFRs**
- [x] Hash/criptografia de dados sensíveis (LGPD)
- [x] Logs estruturados + métricas + alertas
- [x] Idempotência na submissão (retry/circuit breaker: seams preparados, simulados)

**Epic 5 — Qualidade**
- [x] Testes unitários por elo
- [x] Testes de integração da cadeia
- [x] Testes de performance (latência/vazão)

**Epic 6 — Entrega**
- [ ] Documentação final + diagramas
- [ ] README, trade-offs, limitações
- [ ] Declaração de uso de IA + preparação da apresentação (30min)
