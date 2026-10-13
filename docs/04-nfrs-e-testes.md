# 4. NFRs Detalhados e Estratégia de Testes

## 4.1 NFRs Detalhados

- **Latência:** regras O(1), cache de regras, processamento em memória
- **Escalabilidade:** serviço stateless, fila + workers (simulados), batch
- **Segurança/LGPD:** hash com salt no CPF, criptografia de campos sensíveis, logs sem PII, controle de acesso no **API gateway** (antes de a requisição chegar na app)
- **Observabilidade:** logs estruturados (corr. ID), métricas (volume, taxa aprovação/reprovação, latência p50/p95), alertas
- **Resiliência:** retry com backoff exponencial no write do SQLite (`CREDITO_PERSISTENCIA_RETRY_*`), idempotência na submissão, máquina de estados FALHA → EM_AVALIACAO (circuit breaker e fila: seams, ver backlog)

## 4.2 Estratégia de Testes

- **Unitários:** cada elo isolado (aprovado/reprovado/limite) + invariants dos modelos
- **Integração:** cadeia completa, ordem e short-circuit, API, persistência
- **Edge cases:** score no limite (600/599), atrasos no limite (2/3), limite zerado, gastos zerados, dados inválidos (422)
- **Performance:** medição de latência e vazão (meta: 10k/min)

**Cobertura atual:** 41 testes (`pytest -q` em `credito-rotativo/`).

**Resultados medidos:** latência por avaliação **0,44 ms**; vazão
**~369k avaliações/min** (meta do case: 10k/min); latência p50/p95
exposta em `/metricas` (p95 ≈ 1,6 ms na carga dos testes de API).
