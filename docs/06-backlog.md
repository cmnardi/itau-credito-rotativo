# 6. Backlog

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

**Epic 7 — Infraestrutura Local**
- [x] Dockerfile (multi-stage, venv, usuário não privilegiado, healthcheck)
- [x] docker-compose (app + volume de dados SQLite)
- [x] Persistência SQLite opcional (`CREDITO_PERSISTENCIA`)

**Epic 6 — Entrega**
- [x] Documentação final + diagramas
- [x] README, trade-offs, limitações
- [x] Criar Swagger com exemplos (OpenAPI em `/docs`)
- [x] Declaração de uso de IA + preparação da apresentação (30min)
