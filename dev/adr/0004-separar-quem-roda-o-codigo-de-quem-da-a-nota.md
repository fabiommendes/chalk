---
type: adr
status: accepted
tags: [grading, sandbox, security]
created: 2026-11-12
decided: 2026-11-12
creator: claude
---

# Separar quem roda o código de quem dá a nota

## Contexto

O código do aluno pode apagar testes, pular a coleta, criar testes falsos ou imprimir uma nota falsa. Se a nota sair do que roda junto com esse código, ela pode ser forjada (`dev/rfc/modelo-de-seguranca-e-sandbox-do-autograder.md`, "Princípio: separar quem roda de quem dá a nota").

Evidência: `packages/chalk-grader/chalk_grader/profile_grader.py:4-25`.

## Decisão

A correção tem etapas com confiança diferente:

1. Preparo (confiável, fora do sandbox, com rede): instala as dependências do template num cache chaveado pelo hash dos arquivos-chave.
2. Execução de referência: build e testes sobre a solução de referência, no sandbox; os testes do relatório dela são os testes esperados.
3. Build e testes do aluno (não confiáveis, no sandbox, sem rede).
4. Nota (confiável, no chalk): só contam os testes esperados; teste ausente do relatório conta como falha.

Os diretórios de teste e os arquivos confiáveis vêm do template: as cópias do aluno são substituídas e montadas só leitura. O aluno não adiciona dependências; vale o lockfile do template.

## Consequências

- Apagar, pular ou forjar testes não muda a nota.
- Toda questão de código precisa de template e de solução de referência que passe em tudo.
- Mudar testes ou solução não exige invalidar cache, porque a execução de referência roda uma vez por grader.
