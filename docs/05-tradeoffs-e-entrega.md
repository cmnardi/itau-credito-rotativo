# 5. Trade-offs, Limitações e Entrega

## 5.1 Trade-offs

- **Python + FastAPI vs Java/Kotlin:** Python maximiza clareza e velocidade (prazo de 7 dias), deixando tempo para testes, docs e NFRs; Java/Kotlin seria mais alinhado à stack do Itaú, mas mais verboso para o escopo do case
- **CoR puro vs Strategy:** CoR atende ao fluxo sequencial de avaliação; Strategy só se justifica com múltiplos algoritmos de cálculo — decisão adiada
- **CoR + orquestrador vs SAGA na v1:** SAGA só se justifica com side effects transacionais distribuídos; a v1 prepara os seams (estados, eventos, idempotência) para a migração sem refatoração
- **Short-circuit vs avaliação completa:** reprovação imediata economiza processamento, mas perde diagnóstico completo (mitigado com log dos motivos até o ponto de corte)
- **Env vars vs código/YAML:** env vars são o padrão 12-factor (trocáveis por ambiente, sem redeploy); exigem tipagem e defaults (pydantic-settings)

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

O uso de IA é liberado pelo case e deve ser explicitado. Registrar: uso na estruturação deste plano, exploração de padrões (CoR/Strategy) e redação da documentação — o raciocínio técnico, regras e trade-offs são do autor.
