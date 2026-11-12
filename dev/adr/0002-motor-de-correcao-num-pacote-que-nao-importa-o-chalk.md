---
type: adr
status: accepted
tags: [grading, packages]
created: 2026-11-12
decided: 2026-11-12
creator: claude
---

# Motor de correção num pacote que não importa o chalk

## Contexto

O motor de correção (perfis, sandbox, `ProfileGrader`, scoring, guard) vivia em `chalk/autograder/` e dependia de tipos de `chalk.core`. O `chalk-worker` (RFC `dev/rfc/worker-de-correcao-do-codehood-modelo-pull.md`) precisa do mesmo motor, sem quizzes, roster nem a turma do chalk.

Evidência: commit 11ffe3b; `AGENTS.md`, seção "Pacotes"; `packages/chalk-grader/pyproject.toml`.

## Opções

- Manter o motor no chalk e fazer o worker depender do chalk inteiro.
- Extrair o motor para um pacote próprio no mesmo repositório (workspace uv).

## Decisão

O motor é o pacote `chalk-grader` (`packages/chalk-grader/`, `import chalk_grader`), dependência comum do chalk e do `chalk-worker`. Ele não importa nada do chalk, do pandas nem do mdq. A questão chega ao motor como `chalk_grader.task.Task`; `Score`, `Graded`, os motivos simples de desclassificação e os modelos `Autograder`/`Profile`/`Limits`/`Service` são do motor, e `chalk.core` os reexporta.

## Consequências

- O worker instala só o motor, que importa em ~0,1 s.
- Tipos que o motor precisa saem do chalk para o motor, não o contrário.
- Os testes do motor ficam em `packages/chalk-grader/tests/` e não usam a turma de exemplo.
