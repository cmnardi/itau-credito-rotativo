# Sistema de Regras para Crédito Rotativo em Cartão de Crédito

Case do processo seletivo de Engenharia de Software Backend (Itaú).
Simula a avaliação e liberação de crédito rotativo para uma lista de clientes,
aplicando regras de negócio extensíveis (Chain of Responsibility).

## Executar

```bash
cd credito-rotativo
pip install -r requirements.txt
uvicorn app.api.main:app --reload        # API em http://127.0.0.1:8000
pytest -q                                # testes (unitários, integração, performance)
```

## Endpoints

| Método | Path | Descrição |
|---|---|---|
| POST | `/avaliacoes` | Avalia um cliente |
| POST | `/avaliacoes/batch` | Avalia uma lista de clientes |
| GET | `/relatorio` | Aprovados, reprovados e valores liberados |
| GET | `/metricas` | Volume, taxa de aprovação, latência p50/p95 |
| GET | `/saude` | Healthcheck |
| GET | `/docs` | Swagger (OpenAPI) com exemplos de request/response |

```bash
curl -X POST http://127.0.0.1:8000/avaliacoes \
  -H "Content-Type: application/json" \
  -d '{"nome":"Ana Silva","cpf":"123.456.789-00","score_credito":750,
       "valor_fatura":"1000.00","limite_disponivel":"4000.00",
       "atrasos_meses":0,"gastos_ultimos_meses":["1000.00","1000.00",
       "1000.00","1000.00","1000.00","1000.00"]}'
```

Idempotência: envie `X-Idempotency-Key` (opcional); por padrão a chave é o
hash do CPF, então a mesma submissão não reavalia o cliente.

## Arquitetura (Ports & Adapters)

```
API/Adapter (FastAPI) → Caso de Uso (orquestrador) → Cadeia de Regras (CoR) → Persistência
```

- **Domínio puro** (`app/domain`): dataclasses frozen, validação fail-fast,
  regras como funções puras — sem dependência de framework.
- **Chain of Responsibility**: `AbstractRule` (template method) cuida do
  encadeamento e do short-circuit; cada regra implementa apenas `avaliar()`.
  Regras bloqueadoras (R1, R2) reprovam imediatamente; regras de scoring
  (R3–R5) acumulam pesos no `EvaluationContext`.
- **Extensibilidade (Open/Closed)**: nova regra = nova classe concreta
  registrada em `app/domain/rules/__init__.py`.

## Regras

| # | Regra | Tipo | Critério (default) | Peso |
|---|---|---|---|---|
| R1 | Score mínimo | Bloqueio | score ≥ 600 | — |
| R2 | Histórico de atrasos | Bloqueio | atrasos ≤ 2 meses | — |
| R3 | Utilização do limite | Scoring em banda | 10% ≤ uso ≤ 90% (fora: 0 ou metade) | 10 |
| R4 | Estabilidade de gastos | Scoring | variação (dp/média) ≤ 0.30 | 10 |
| R5 | Perfil de gastos | Scoring | fatura ≤ média × 1.5 | 10 |

**Decisão:** sem bloqueio **e** score acumulado ≥ 20 (máx 30 → 2 dos 3 critérios).

**Valor máximo:** `min(fatura × 1.0, limite_total × 0.50, 10.000) × ajuste`,
onde `ajuste = 0.50 + 0.50 × peso_acumulado / 30` (quanto melhor o perfil,
maior o valor dentro do teto).

## Configuração (env vars, padrão 12-factor)

Todas as regras e o cálculo são parametrizáveis via `CREDITO_*`
(ex.: `CREDITO_SCORE_MINIMO=600`, `CREDITO_LIMITE_APROVACAO=20`).
Carregadas por `pydantic-settings`: tipadas, com defaults, validadas no boot.
Veja a tabela completa em `plano.md` (seção 7).

## NFRs

- **Latência/vazão:** regras O(1), cadeia construída uma vez (cache),
  tudo em memória — teste de performance valida 10k avaliações/min.
- **LGPD:** CPF hasheado (SHA-256 + salt) no adapter; nada de PII
  persistido ou logado.
- **Observabilidade:** logs via `logging` e métricas em memória
  (volume, taxa de aprovação, latência p50/p95) em `/metricas`.
- **Resiliência:** idempotência na submissão; máquina de estados
  (RECEBIDO → EM_AVALIACAO → AVALIADO/FALHA) permite retomada.

## Trade-offs (resumo)

- **Python + FastAPI** vs Java/Kotlin: clareza e velocidade no prazo de 7 dias;
  mais verboso em Java, mas mais alinhado à stack do Itaú.
- **CoR + orquestrador** vs SAGA na v1: SAGA só se justifica com side effects
  transacionais distribuídos; a v1 prepara os seams (estados, eventos,
  idempotência) para migração futura sem refactor.
- **Env vars** vs YAML: padrão 12-factor; exige tipagem (pydantic-settings).

## Uso de IA

IA usada para: estruturação do plano, exploração dos padrões (CoR/Strategy),
redação da documentação e implementação inicial. O raciocínio técnico, as
regras de negócio e os trade-offs foram definidos e revisados pelo autor.

Documentação completa: `plano.md` (raiz do repositório).
