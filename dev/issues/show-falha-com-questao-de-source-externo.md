---
type: issue
status: completed
tags: [cli, mdq, codehood]
kind: defect
created: 2026-11-12
creator: claude
---

# `chalk show QUIZ/QUESTION` falha quando a questão vem de `source:` fora do quiz

Com `source: ../questions/logico/backtracking/operador-de-corte.md` no `conf.yaml` (o caso de reusar o banco de um curso codehood), `chalk show p1/corte` sai com:

```
Error: '.../questions/logico/backtracking/operador-de-corte.md' is not in the subpath of '.../p1'
```

Causa: `chalk/question/mdq.py:_render_base_fields` faz `self._path.relative_to(self.quiz.root)`. Usar `os.path.relpath` (ou relativo à raiz da turma). `chalk autograde` e `chalk show p1` funcionam com a mesma questão.
