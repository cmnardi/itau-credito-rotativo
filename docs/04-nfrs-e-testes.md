# 4. NFRs Detalhados e Estratégia de Testes

## 4.1 NFRs Detalhados

- **Latência:** regras O(1), cache de regras, processamento em memória
- **Escalabilidade:** serviço stateless, fila + workers (simulados), batch
- **Segurança/LGPD:** hash com salt no CPF, criptografia de campos sensíveis, RBAC simulado, logs sem PII
- **Observabilidade:** logs estruturados (corr. ID), métricas (volume, taxa aprovação/reprovação, latência p50/p95), alertas
- **Resiliência:** retries com backoff, circuit breaker, idempotência na submissão

## 4.2 Estratégia de Testes

- **Unitários:** cada elo isolado (aprovado/reprovado/limite)
- **Integração:** cadeia completa, ordem e short-circuit
- **Edge cases:** score no limite, atrasos no limite, limite zerado, dados ausentes
- **Performance:** medição de latência e vazão (meta: 10k/min)

Cobertura atual: 38 testes (`pytest -q` em `credito-rotativo/`) — unitários por elo, integração da cadeia e da API, e testes de performance que validam a meta de vazão.
