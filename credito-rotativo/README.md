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

## Docker

```bash
docker compose up --build     # API em http://127.0.0.1:8000 (SQLite em volume)
docker compose down -v        # para e remove o volume de dados
```

Se a porta 8000 da máquina já estiver em uso, mapeie em outra:

```bash
CREDITO_PORTA=8001 docker compose up --build   # API em http://127.0.0.1:8001
```

Para subir **com banco em memória** (sem persistência entre reinícios):

```bash
CREDITO_PERSISTENCIA=memoria docker compose up --build
```

O compose sobe a aplicação com todas as dependências. Com SQLite,
as avaliações ficam em `/data/avaliacoes.db` (volume nomeado) e
sobrevivem a reinícios do container. Para rodar sem Docker:
`uvicorn app.api.main:app` (padrão é memória).

## Endpoints

| Método | Path | Descrição |
|---|---|---|
| POST | `/avaliacoes` | Avalia um cliente |
| POST | `/avaliacoes/batch` | Avalia uma lista de clientes |
| GET | `/relatorio` | Aprovados, reprovados e valores liberados (JSON; `Accept: text/csv` → CSV) |
| GET | `/metricas` | Volume, taxa de aprovação, latência p50/p95, **replays** (idempotência) e **alertas** (erros/falhas) |
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
hash do CPF, então a mesma submissão não reavalia o cliente. O reenvio não
some da observabilidade: ele vira `replays` no `GET /metricas`, enquanto
`total` continua contando só decisões novas (sem inflar as taxas).

### Exportar o relatório em CSV (content negotiation)

O `GET /relatorio` atende JSON por padrão; pedindo `Accept: text/csv` o mesmo
recurso devolve o download em CSV (`Content-Disposition: attachment`):

```bash
curl -H "Accept: text/csv" http://127.0.0.1:8000/relatorio -o relatorio.csv
```

O arquivo tem duas seções — **RESUMO** (totais, taxa de aprovação,
`gerado_em`) e **DETALHES** (uma linha por avaliação) — e usa `;` como
separador, para abrir direto no Excel pt-BR:

```csv
RESUMO
gerado_em;2026-10-12T10:00:00+00:00
total_avaliacoes;2
aprovados;1
reprovados;1
valor_total_liberado;1000.00
taxa_aprovacao;0.5

DETALHES
timestamp;status;valor_liberado;cpf_hash;motivos;regras_aplicadas;idempotency_key
2026-10-12T09:58:11+00:00;aprovado;1000.00;bd81eb5f...;;ScoreMinimoRule | ...;a2d11401...
```

Programaticamente, leia a partir da seção DETALHES — com `csv.reader(f,
delimiter=";")` procurando a linha `DETALHES`, ou no pandas pulando as linhas
do RESUMO (`pd.read_csv("relatorio.csv", sep=";", skiprows=9)`, contando a
linha em branco). O CSV leva o `cpf_hash` — nunca o CPF — porque a lista de
clientes precisa ser rastreável sem expor PII.

### Collection Postman (endpoints, variações e testes)

[`postman/credito-rotativo.postman_collection.json`](postman/credito-rotativo.postman_collection.json)
cobre os 5 endpoints com **17 requests e 86 testes** que validam o resultado
esperado de cada caminho das regras:

| Pasta | Cobre |
|---|---|
| 01 · Saúde e contrato | healthcheck (`/saude`) e contrato OpenAPI |
| 02 · Avaliações | aprovado (30 pts), aprovado com perfil inativo (25 pts + motivo de alerta), reprovado por R1 (bloqueio), por R2 (bloqueio), por pontuação (10 pts) e com todas as regras aplicadas (15 pts) + erros 400 e 422 |
| 03 · Idempotência | reenvio do mesmo CPF com payload diferente → servido pelo cache (replay) |
| 04 · Batch | lista mista: aprovado + reprovado, na ordem |
| 05 · Relatório | RF5 em JSON e em CSV (content negotiation) |
| 06 · Operação | invariantes do `/metricas` (aprovados + reprovados = total, p50 ≤ p95, alertas) e replay contabilizado |

```bash
# Postman: importe o JSON e use "Run Collection" (a pasta 03 passa a
# chave entre requests; a variável da collection é `base_url`, padrão 8001)
# Sem Postman (mesmos testes, servem de smoke test na CI):
npx newman run postman/credito-rotativo.postman_collection.json
```

Os payloads usam CPFs próprios da collection (`910.220.330-xx`, distintos do
dataset) e os valores esperados assumem a **configuração padrão** — trocando
as `CREDITO_*`, recalibre os números dentro dos testes.

### Dataset fictício (RF1 — lista de clientes)

O case pede simular a avaliação **para uma lista de clientes**: ela está em
`data/clientes_ficticios.json`, com 14 perfis fictícios (nomes e CPFs de
mentira, sem checksum válido) no formato exato do body de
`POST /avaliacoes/batch`:

```bash
curl -X POST http://127.0.0.1:8000/avaliacoes/batch \
  -H "Content-Type: application/json" \
  -d @data/clientes_ficticios.json     # 14 clientes → 9 aprovados, 5 reprovados
```

Os perfis cobrem os caminhos das 5 regras: bloqueios nas bordas (score
599/600, 2/3 atrasos), aprovação com 2 dos 3 critérios (uso 95%, fatura 2× a
média, variação 0.55), perfil inativo (uso 4% → meio ponto), reprovação com
0 pontos, o teto de 10.000 e o limite de 50% do limite total. O desfecho
esperado de cada cliente está na tabela viva em
`tests/integration/test_dataset.py`, que roda o dataset de ponta a ponta
(schema → API → cadeia → relatório → CSV).

### Alertas em `/metricas` (NFR: "alertas para possíveis erros ou falhas")

O `GET /metricas` devolve as métricas **mais** os alertas avaliados contra
os limites `CREDITO_ALERTA_*` (calibráveis por env var):

| Código | Severidade | Dispara quando | Env var (default) |
|---|---|---|---|
| `latencia_p95_acima_do_slo` | crítico | p95 da latência > limite | `CREDITO_ALERTA_LATENCIA_P95_MS` (1000 = NFR ≤ 1s) |
| `taxa_de_erro_acima_do_limite` | crítico | falhas ÷ processado > limite | `CREDITO_ALERTA_TAXA_ERRO_MAX` (0.05) |
| `taxa_de_reprovacao_anomala` | warning | reprovações ÷ total ≥ limite | `CREDITO_ALERTA_REPROVACAO_MIN` (0.90) |

```json
{
  "total": 14, "aprovacoes": 9, "reprovacoes": 5, "falhas": 1,
  "taxa_aprovacao": 0.6429, "taxa_reprovacao": 0.3571, "taxa_erro": 0.0667,
  "ultimo_erro": "RuntimeError", "latencia_p50_ms": 1.2, "latencia_p95_ms": 3.4,
  "status": "alerta",
  "alertas": [
    {
      "codigo": "taxa_de_erro_acima_do_limite",
      "severidade": "critico",
      "mensagem": "taxa de erro 6.67% acima do limite 5.00% — última falha: RuntimeError",
      "valor": 0.0667,
      "limite": 0.05
    }
  ]
}
```

`status` é `ok` sem alerta e `alerta` com um ou mais ativos. Cada
**transição** também vira log estruturado (`alerta_disparado` em WARNING,
`alerta_encerrado` em INFO) — quem faz polling em `/metricas` não gera
evento repetido. A avaliação é uma função pura do snapshot (testável sem
dormir) e as falhas entram pelo caminho de exceção da cadeia.

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
  (volume, taxa de aprovação, latência p50/p95, replays idempotentes) em
  `/metricas`, que também avalia os **alertas** de erros/falhas (abaixo).
- **Resiliência:** idempotência na submissão; retry com backoff exponencial
  no write do SQLite (`CREDITO_PERSISTENCIA_RETRY_*`); máquina de estados
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
