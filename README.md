# Case — Sistema de Regras para Crédito Rotativo em Cartão de Crédito

**Processo Seletivo — Engenharia de Software Backend (Itaú)**
**Prazo:** 7 dias corridos
**Stack:** Python 3.12 + FastAPI (API) + Pytest (testes) — escolhida por clareza, velocidade de desenvolvimento e ecossistema de testes; justificativa e trade-offs vs Java/Kotlin em [trade-offs](docs/05-tradeoffs-e-entrega.md)
**Padrão central:** Chain of Responsibility (Strategy avaliado na implementação, se necessário)

## Índice da documentação

| Documento | Conteúdo |
|---|---|
| [docs/01-contexto-e-requisitos.md](docs/01-contexto-e-requisitos.md) | Contexto do negócio, requisitos funcionais e não funcionais |
| [docs/02-arquitetura.md](docs/02-arquitetura.md) | Diagramas, modelo de domínio, estrutura do projeto, Ports & Adapters, evolução para SAGA |
| [docs/03-regras-e-configuracao.md](docs/03-regras-e-configuracao.md) | Regras R1–R5, parametrização (env vars), modelo de scoring, design da cadeia, cálculo do valor máximo |
| [docs/04-nfrs-e-testes.md](docs/04-nfrs-e-testes.md) | NFRs detalhados (latência, escala, LGPD, observabilidade, resiliência) e estratégia de testes |
| [docs/05-tradeoffs-e-entrega.md](docs/05-tradeoffs-e-entrega.md) | Trade-offs, limitações, evoluções, entregáveis, declaração de uso de IA |
| [docs/06-backlog.md](docs/06-backlog.md) | Backlog por épica (progresso da implementação) |
| [docs/07-apresentacao.md](docs/07-apresentacao.md) | Roteiro da apresentação (30 min), demo e Q&A |

## Código

A implementação está em [`credito-rotativo/`](credito-rotativo/) — instruções de execução, endpoints e exemplos no [README de lá](credito-rotativo/README.md).

Para exercitar a API de ponta a ponta existe a [collection do Postman](credito-rotativo/postman/credito-rotativo.postman_collection.json): 17 requests com 86 testes cobrindo as variações aprovado/reprovado (uma por caminho das 5 regras), idempotência/replay, batch, relatório JSON/CSV e `/metricas`. Importe no Postman ou rode sem ele com `npx newman run postman/credito-rotativo.postman_collection.json`.
