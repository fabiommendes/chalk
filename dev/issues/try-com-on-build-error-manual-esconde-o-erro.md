---
type: issue
status: backlog
tags: [codehood, autograder, cli]
kind: defect
created: 2026-11-13
creator: claude
---

# `--try` com `on_build_error: manual` esconde o erro do compilador

`chalk codehood autograde --try GRADER FILE` com `on_build_error: manual` imprime só `Left for manual grading.`. Para ver por que a resposta não compilou, foi preciso tirar a linha do `grader.yaml`, rodar de novo e restaurar.

Proposta: `--try` sempre mostra a saída do build quando ele falha, qualquer que seja o `on_build_error`. É um comando de diagnóstico.
