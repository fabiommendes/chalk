---
type: issue
status: backlog
tags: [grading]
relatedTo: [chalk-autograde-all-apaga-os-ajustes-manuais]
kind: defect
created: 2026-11-12
creator: claude
---

# Ajustes não são gravados no grades.csv

`models.ResponseGrade.adjustments` existe e `Grades.set_score` aceita ajustes, mas `save_grades_to_path` (`chalk/core/grades.py`) só grava a nota e as linhas extras de `EXTRA_FIELDS = ("feedback", "notes")`. Ajuste definido em memória some no próximo `save`.

Nenhum comando cria ajustes hoje e nada os aplica na nota final, então o problema não aparece para o usuário. Aparece quando alguém implementar ajustes manuais.

Proposta: incluir `adjustments` em `EXTRA_FIELDS`, uma linha `adjustments` por aluno, com os ajustes serializados por `Adjustment.serialize` e separados por `;`. Muda o formato do `grades.csv` (só acrescenta linhas). Conferir se o codehood lê esse arquivo do quiz (acho que lê só o `grades.csv` da raiz).
