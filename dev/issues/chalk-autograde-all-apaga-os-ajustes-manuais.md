---
type: issue
status: completed
tags: [grading]
kind: defect
created: 2026-11-12
creator: claude
closed: 2026-11-12
---

# chalk autograde --all apaga os ajustes manuais

Ao recorrigir (`chalk autograde <quiz>/<questão> --all`), o grade novo é gravado com `adjustments=None` (`chalk/cli/autograde_cmd.py`). Ajustes que o professor fez à mão (pontos dados, atraso, questão anulada) somem sem aviso.

Comportamento mantido na extração do `chalk-grader` (11ffe3b) para não mudar duas coisas de uma vez.

Decidir:

- preservar os ajustes existentes e aplicar sobre a nova nota (provável), ou
- manter o comportamento e avisar quantos ajustes serão apagados, com confirmação.

---
by: claude

Corrigido: `run_autograder` não passa mais `adjustments`, então o regrade mantém os ajustes da resposta. O usuário decidiu que os ajustes nunca são apagados.

Achado no caminho: com `--all`, uma nota que mudava era mostrada (`antiga -> nova`) e descartada por um `continue` antes de `set_score`. Só notas iguais eram regravadas. Corrigido junto. Testes em `tests/test_autograder_chalk.py::TestRegrade`.

Os ajustes ainda não chegam ao disco: ver `ajustes-nao-sao-gravados-no-grades-csv`.
