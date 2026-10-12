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

**Epic 6 — Infraestrutura Local**
- [x] Dockerfile (multi-stage, venv, usuário não privilegiado, healthcheck)
- [x] docker-compose (app + volume de dados SQLite)
- [x] Persistência SQLite opcional (`CREDITO_PERSISTENCIA`)

**Epic 7 — Fechamento de Gaps (revisão vs case)**
- [x] Logs estruturados reais — JSON por linha, eventos (iniciada/concluida/falha/replay), correlation_id, sem PII
- [ ] Autenticação/autorização simulada — case pede "controle de acesso restrito, autenticação, autorização"
- [ ] Retry com backoff no write do SQLite — docs prometem resiliência a indisponibilidade temporária
- [ ] Alertas no `/metricas` — case pede "alertas para possíveis erros ou falhas"
- [x] Dataset fictício `data/clientes_ficticios.json` — case fala em "lista de clientes" (14 perfis = payload do `/avaliacoes/batch`, testado de ponta a ponta)
- [x] Exportação do relatório em CSV — plus rápido além do JSON (content negotiation: `Accept: text/csv` no `GET /relatorio`)
- [ ] Atualizar `docs/04` e o roteiro da apresentação para refletir a realidade do código

**Epic Entrega**
- [x] Documentação final + diagramas
- [x] README, trade-offs, limitações
- [x] Criar Swagger com exemplos (OpenAPI em `/docs`)
- [x] Declaração de uso de IA + preparação da apresentação (30min)
