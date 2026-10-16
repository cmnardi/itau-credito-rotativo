# 5. Trade-offs, Limitações e Entrega

## 5.1 Trade-offs

- **Python + FastAPI vs Java/Kotlin:** Python maximiza clareza e velocidade (prazo de 7 dias), deixando tempo para testes, docs e NFRs; Java/Kotlin seria mais alinhado à stack do Itaú, mas mais verboso para o escopo do case
- **CoR puro vs Strategy:** CoR atende ao fluxo sequencial de avaliação; Strategy só se justifica com múltiplos algoritmos de cálculo — decisão adiada
- **CoR + orquestrador vs SAGA na v1:** SAGA só se justifica com side effects transacionais distribuídos; a v1 prepara os seams (estados, eventos, idempotência) para a migração sem refatoração
- **Short-circuit vs avaliação completa:** reprovação imediata economiza processamento, mas perde diagnóstico completo (mitigado com log dos motivos até o ponto de corte)
- **Env vars vs código/YAML:** env vars são o padrão 12-factor (trocáveis por ambiente, sem redeploy); exigem tipagem e defaults (pydantic-settings)
- **SQLite vs Postgres no Docker:** o case aceita mocks e a v1 é single-node — SQLite dá persistência real sem infra extra; o repositório está atrás de interface (`CREDITO_PERSISTENCIA`), então migrar para Postgres é uma nova implementação + env var, sem mudança no caso de uso

## 5.2 Limitações e Evoluções

- Sem integrações reais (mocks aceitos pelo case)
- Versão inicial single-node; evoluir para fila/workers reais
- Evoluções: Strategy para cálculo, regras com ML, dashboard operacional

## 5.3 Entregáveis

- [x] Documentação arquitetural (docs/)
- [x] Diagramas (Mermaid)
- [x] Estratégia de testes
- [x] Justificativa de decisões e trade-offs
- [x] Limitações e evoluções
- [x] README com instruções (credito-rotativo/README.md)

## 5.4 Declaração de Uso de IA

O uso de IA é liberado pelo case e deve ser explicitado ("como e em qual
momento"). Declaro:

**Metodologia — SSD (Spec-Driven Development).** A solução foi feita sob
especificação primeiro: a **especificação do problema proposto no case foi
discutida e detalhada com a IA antes das definições** — requisitos
funcionais e não funcionais, regras R1–R5 com seus thresholds, modelo de
scoring, fórmula de valor, padrões (CoR/Strategy/SAGA) e decisões de
escopo foram negociados e revisados nessa etapa, com o autor validando
cada definição. **Só após as definições acertadas a implementação foi
iniciada**, Épic por Épic a partir da especificação (o backlog em
`docs/06` espelha esse fluxo). Ou seja: a IA detalhou a especificação com
o autor primeiro; o código veio depois — e não o contrário.

**Como foi usada:** IA como ferramenta de estruturação e par de
programação, com revisão humana de cada decisão.

**Em qual momento:**
1. **Planejamento** — estruturação do plano de implementação, exploração
   dos padrões (CoR/Strategy/SAGA) e diagramas Mermaid
2. **Implementação** — geração do esqueleto do código (domínio, cadeia,
   API, testes) com revisão e correções do autor (ex.: bug na transição
   para APROVADO, casos de teste de idempotência)
3. **Documentação** — redação de README, trade-offs, testes e roteiro da
   apresentação

**O que é do autor:** a definição das regras de negócio (R1–R5) e seus
thresholds, o modelo de scoring (20/30), a fórmula do valor máximo e as
justificativas dos trade-offs — todas as decisões técnicas são
discutidas na apresentação.
