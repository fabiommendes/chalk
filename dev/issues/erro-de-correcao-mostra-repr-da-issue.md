---
type: issue
status: completed
tags: [cli, grading]
kind: defect
created: 2026-11-12
creator: claude
---

# Erro de correção mostra o `repr` da `Issue`

`chalk autograde` mostra a resposta inválida assim:

```
* 1001: Error: Issue(code='invalid-response', message="Response id 'b' not found in
choices", severity=<IssueLevel.ERROR: 2>, scopes=frozenset({'response'}))
```

`chalk/question/base.py:fail` empacota a `Issue` em `ValueError(issue)`, e quem imprime usa `str(exc)`. Deveria mostrar só a mensagem: `Error: Response id 'b' not found in choices`. Conferir também `chalk/core/issue.py:list_of_issues`, que não desempacota `ValueError(Issue)`.
