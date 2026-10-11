# 1. Contexto e Requisitos

## 1.1 Contexto

O cartão de crédito possui uma modalidade de crédito rotativo liberada automaticamente para clientes com perfil aprovado. A liberação depende de regras complexas baseadas em histórico de crédito, perfil de gastos e comportamento recente. A solução deve simular a avaliação e liberação para uma lista de clientes.

## 1.2 Requisitos Funcionais

- **RF1:** Receber dados fictícios de clientes (nome, CPF, score de crédito, valor da fatura atual, limite disponível, nº de atrasos, comportamento de gastos nos últimos meses)
- **RF2:** Avaliar regras que definem se o crédito rotativo pode ser liberado
- **RF3:** Calcular o valor máximo de crédito rotativo para cada cliente elegível
- **RF4:** Permitir inclusão de novas regras sem alterar a estrutura principal (Chain of Responsibility)
- **RF5:** Gerar relatório com aprovados, reprovados e respectivos valores liberados
- **RF6:** Documentar critérios de decisão e justificar as regras aplicadas

## 1.3 Requisitos Não Funcionais

| NFR | Meta |
|---|---|
| Latência de decisão | ≤ 1s por avaliação |
| Escalabilidade | Picos de até 10.000 avaliações/min |
| Precisão/consistência | Sem liberações indevidas ou bloqueios incorretos |
| Extensibilidade | Novas regras sem refatoração do código base |
| Segurança/LGPD | Criptografia, controle de acesso, autenticação/autorização |
| Observabilidade | Métricas, logs estruturados, alertas |
| Resiliência | Continuidade e integridade em falhas temporárias |

Detalhamento de como cada NFR é atendido: [04-nfrs-e-testes.md](04-nfrs-e-testes.md).
