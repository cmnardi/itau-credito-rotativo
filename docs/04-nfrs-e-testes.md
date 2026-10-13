# 4. NFRs Detalhados e Estratégia de Testes

## 4.1 NFRs Detalhados

- **Latência:** regras O(1), cadeia montada uma vez (cache), processamento em memória
- **Escalabilidade:** serviço stateless, batch síncrono em memória (`POST /avaliacoes/batch`); fila + workers ficam como evolução (ver backlog)
- **Segurança/LGPD:** hash com salt no CPF (nenhuma PII persistida ou logada em claro), logs sem PII, controle de acesso no **API gateway** (antes de a requisição chegar na app)
- **Observabilidade:** logs estruturados (corr. ID), métricas (volume, taxa aprovação/reprovação, replays idempotentes, latência p50/p95), alertas
- **Resiliência:** retry com backoff exponencial no write do SQLite (`CREDITO_PERSISTENCIA_RETRY_*`), idempotência na submissão, máquina de estados FALHA → EM_AVALIACAO (circuit breaker e fila: seams, ver backlog)

## 4.2 Estratégia de Testes

- **Unitários:** cada elo isolado (aprovado/reprovado/limite) + invariants dos modelos
- **Integração:** cadeia completa, ordem e short-circuit, API, persistência
- **Edge cases:** score no limite (600/599), atrasos no limite (2/3), limite zerado, gastos zerados, dados inválidos (422)
- **Performance:** medição de latência e vazão (meta: 10k/min)

**Cobertura atual:** 105 testes com **100% das linhas** cobertas
(`pytest -q --cov=app` em `credito-rotativo/`): unitários por elo,
integração (cadeia, API, persistência) e performance.

**Resultados medidos** (execução local, `tests/performance/`):
- latência por avaliação: **0,35–0,79 ms** (NFR ≤ 1 s)
- vazão em memória: **382k–460k avaliações/min** (meta do case: 10k/min)
- pela API (500 POSTs no container): p50 **0,19 ms**, p95 **0,25 ms**
  expostos em `/metricas` — a carga HTTP sequencial do teste ficou em
  ~78 req/s, limite do cliente do teste, não do serviço
