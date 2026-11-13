---
type: issue
status: completed
tags: [grading, codehood, autograder]
kind: feature
created: 2026-11-12
creator: claude
---

# Quiz com `source:` não usa o grader de `graders/<path>/`

Num repositório que é curso codehood, a questão de código `questions/logico/aritmetica/fatorial-com-is.md` tem grader em `graders/logico/aritmetica/fatorial-com-is/` (`grader.yaml`, `template/`, `solution/`). `chalk codehood autograde --check` e `--try` usam esse grader.

Um quiz do chalk que reusa a questão com `source: ../questions/logico/aritmetica/fatorial-com-is.md` trata a questão como `essay`, e `chalk autograde p1/fatorial` responde `not graded.` para todos. Para corrigir, o professor teria de copiar o grader para `p1/fatorial/` no formato de script do chalk.

Proposta: quando a questão vem de `questions/<path>.md` de um curso codehood e existe `graders/<path>/grader.yaml`, usar esse grader (o mesmo caminho de `chalk/codehood_autograde.py:find_graders` e `make_grader`). Um grader na pasta da questão do quiz continua tendo prioridade.
