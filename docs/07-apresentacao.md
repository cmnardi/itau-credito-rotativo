# 7. Apresentação (30 min) — Roteiro

Formato livre (slides + demo ao vivo). Estrutura pedida no case:
contexto → decisões e trade-offs → qualidade/operacão/evolução → estratégia ampliada.

## Cronograma

| Bloco | Tempo | O que mostra |
|---|---|---|
| 1. Contexto da solução + demo | 7 min | Problema, arquitetura, regras; demo de 2 curl |
| 2. Decisões técnicas e trade-offs | 8 min | Padrões, stack, config, banco |
| 3. Qualidade, operação e evolução | 8 min | Testes, métricas, LGPD, resiliência, SAGA |
| 4. Estratégia ampliada | 5 min | Como priorizei e o que ficou de fora |
| Encerramento | 2 min | Limitações + o que faria a seguir |
| **Total** | **30 min** | + 30 min de discussão |

---

## Bloco 1 — Contexto da solução (7 min)

**Slide 1 — O problema (1 min)**
> Avaliar e liberar crédito rotativo para uma lista de clientes, com regras
> de negócio complexas (histórico de crédito, perfil de gastos, comportamento
> recente), extensível sem refatorar o motor, entregando relatório e
> respeitando 7 NFRs — latência ≤1s, 10k avaliações/min, LGPD, observabilidade.

**Slide 2 — Arquitetura (2 min)**
> Ports & Adapters em 4 camadas: `api → application → domain ← infrastructure`.
> O domínio é puro (sem framework) — testável sem HTTP/banco.
> Fluxo: validação → cadeia de regras → decisão → cálculo do valor →
> persistência → relatório. Diagrama de componentes (Mermaid).

**Slide 3 — Padrão central: Chain of Responsibility (2 min)**
> `AbstractRule` com template method: a base faz encadeamento e
> short-circuit; cada regra implementa só `avaliar()`.
> - **Bloqueio (R1 score, R2 atrasos):** reprovam e cortam a cadeia
> - **Scoring (R3, R4, R5):** acumulam peso no `EvaluationContext`
> - **Decisão:** sem bloqueio **e** `peso ≥ 20` (máx 30 → 2 de 3 critérios)
> - Nova regra = nova classe + registro no `REGISTRY` (Open/Closed)

**Slide 4 — Demo ao vivo (2 min)**
```bash
# aprovado (score 750, perfil estável → 30/30 → valor 1000.00)
curl -X POST localhost:8000/avaliacoes -H "Content-Type: application/json" -d '{
  "nome":"Ana Silva","cpf":"123.456.789-00","score_credito":750,
  "valor_fatura":"1000.00","limite_disponivel":"4000.00","atrasos_meses":0,
  "gastos_ultimos_meses":["1000.00","1200.00","900.00","1100.00","1000.00","1000.00"]}'

# reprovado por atrasos (5 > 2 → short-circuit na R2, só R1 aplicada)
# depois: GET /relatorio e GET /metricas mostram agregação e latência
```
> Enfatizar: `regras_aplicadas` mostra o corte da cadeia; `/docs` tem os
> exemplos clicáveis.

---

## Bloco 2 — Decisões técnicas e trade-offs (8 min)

Cada trade-off em 4 tempos: **decisão / alternativa / por quê / quando reavaliar**.

**1. Python + FastAPI vs Java/Kotlin (1 min)**
> Alternativa mais alinhada à stack do Itaú seria Java/Kotlin; escolhi
> Python por clareza e velocidade no prazo de 7 dias, deixando tempo para
> testes e NFRs. Reavaliar se o projeto virasse produto de time Java.

**2. CoR vs Strategy (2 min)**
> O fluxo é sequencial e fixo (bloqueio → scoring → decisão) — CoR atende
> naturalmente. Strategy entraria com fórmulas de cálculo intercambiáveis
> (regras de valor distintas por produto); decisão adiada, com seam aberto
> (método `_calcular_valor` isolado no orquestrador).

**3. CoR + orquestrador vs SAGA (2 min)**
> A avaliação é read-only: regras puras + persistência do resultado — sem
> side effects a compensar, então SAGA seria complexidade sem benefício.
> Em produção, quando houver reserva de limite + contrato + notificação,
> o orquestrador vira step de um SAGA (Temporal) e a máquina de estados
> (RECEBIDO → EM_AVALIACAO → AVALIADO/FALHA) + idempotency key já
> sustentam a retomada.

**4. Short-circuit vs avaliação completa (1 min)**
> Reprovação imediata economiza processamento, mas perde diagnóstico do
> restante; mitigamos mantendo `motivos` até o ponto de corte —
> `regras_aplicadas` documenta o corte.

**5. Env vars vs YAML em código (1 min)**
> 12-factor: trocar threshold por ambiente sem redeploy; `pydantic-settings`
> dá tipagem, defaults e validação no boot (fail fast). Ex.: mudar
> `CREDITO_SCORE_MINIMO` não mexe em código nem testes.

**6. SQLite vs Postgres no Docker (1 min)**
> Case aceita mocks e a v1 é single-node: SQLite dá persistência real sem
> infra extra, e o repositório está atrás de interface (`CREDITO_PERSISTENCIA`)
> — trocar por Postgres = nova implementação + env var, zero mudança
> no caso de uso.

---

## Bloco 3 — Qualidade, operação e evolução (8 min)

**Testes (2 min)**
> Pirâmide: 41 testes — unitários por elo (limites exatos: score 600/599,
> atrasos 2/3), integração (ordem, short-circuit, idempotência,
> persistência entre "reinícios"), API (200/422/headers) e performance.
> Números: **0,44 ms/avaliação, ~369k avaliações/min** (meta: 10k/min),
> latência p95 medida em `/metricas`.

**Observabilidade (2 min)**
> `/metricas`: volume, taxa aprovação/reprovação, latência p50/p95,
> falhas e replays idempotentes (em memória — em produção, Prometheus).
> Logs estruturados via
> logging sem PII. Alertas avaliados no próprio endpoint e logados só na
> transição: latência p95 acima do SLO, taxa de erro acima de 5% (estado
> FALHA) e reprovação anômala ≥ 90% — limites calibráveis em
> `CREDITO_ALERTA_*`.

**Segurança/LGPD (1 min)**
> CPF hasheado (SHA-256 + salt) no adapter — o domínio nunca vê o CPF
> em claro; nem o relatório nem as métricas expõem PII. Salt em env var
> (em produção: KMS/vault). Usuário não privilegiado no container,
> healthcheck no compose.

**Resiliência (1 min)**
> Idempotência por chave (header `X-Idempotency-Key` ou hash do CPF):
> retry não reavalia. Máquina de estados com FALHA → EM_AVALIACAO
> (retry idempotente). SQLite em volume = dados sobrevivem a reinício,
> e o write tem retry com backoff exponencial (`CREDITO_PERSISTENCIA_RETRY_*`)
> contra indisponibilidade temporária — só erro transitório retenta, e cada
> tentativa vira log `persistencia_retry`.

**Evolução (2 min)**
> - Workflow engine (Temporal) no lugar do orquestrador — sem tocar nas regras
> - Fila + workers para picos (batch já existe como endpoint)
> - Postgres + réplicas, Prometheus/Grafana, RBAC real
> - Strategy para fórmulas de valor por produto; regras com ML (score alt.)

---

## Bloco 4 — Estratégia ampliada (5 min)

**Como priorizei (2 min)**
> 1. Requisitos → modelo de domínio e invariants (fail-fast) — base de tudo
> 2. Padrão da cadeia + decisão de escopo (CoR vs SAGA) — evita over-engineering
> 3. Regras parametrizáveis (env vars) — mudar regra sem deploy
> 4. Orquestrador + cálculo do valor + relatório (fecha RF2–RF5)
> 5. NFRs: idempotência, métricas, LGPD, Docker
> 6. Testes + Swagger + documentação
> Cada etapa entregou valor testável; a máquina de estados e os seams de
> SAGA vieram depois, quando já existia fluxo a proteger.

**O que ficou de fora e por quê (2 min)**
> - Autenticação/autorização na app — fica no **API gateway**, antes do tráfego chegar aqui (case: "controle de acesso restrito")
> - Fila/workers reais (batch em memória atende 10k/min medido)
> - Eventos de domínio publicados (seam no orquestrador, sem broker)
> - Integrações bancárias (fora do escopo)

**Encerramento (1 min)**
> Limitações conhecidas: single-node, métricas em memória, auth
> delegada ao API gateway (não implementada na aplicação).
> Próximo passo: productionizar observabilidade (Prometheus) e
> transportar a cadeia para a fila de avaliação.

---

## Q&A provável (30 min de discussão)

| Pergunta | Resposta em 30s |
|---|---|
| Por que não Java? | Velocidade no prazo; trade-off documentado; o padrão (CoR) se replica 1:1 em qualquer linguagem |
| Como adiciono uma regra? | Nova classe + registro no `REGISTRY` + env var — sem tocar no motor; posso mostrar ao vivo |
| O 20/30 veio de onde? | 2 de 3 critérios de negócio — threshold em env var, calibrável sem deploy; dados reais calibrariam |
| Escala real? | Medido: 369k/min vs 10k exigidos; garganto real seria I/O de banco — daí fila + workers |
| Por que idempotência por CPF? | Evita reavaliação em retry de rede; header manual cobre reavaliação deliberada |
| E o short-circuit esconde diagnóstico? | `motivos` até o corte + `regras_aplicadas` mostram exatamente onde parou |
| LGPD: e o salt? | Env var no case; produção: KMS/vault com rotação |
| SQLite aguenta produção? | Não é o plano: interface de repositório isola a troca por Postgres |
| Como testaria em produção? | Load test com os dados fictícios, contrato de API (OpenAPI) em CI, métricas com SLO/alertas |

## Checklist pré-apresentação

- [ ] `docker compose up --build` testado na máquina (não é este ambiente)
- [ ] `pytest -q` verde antes da demo
- [ ] `/docs` aberto em aba separada para o bloco 1
- [ ] Terminal com os comandos da demo prontos (bloco 1)
- [ ] Revisar `docs/05-tradeoffs-e-entrega.md` (perguntas de trade-off)
