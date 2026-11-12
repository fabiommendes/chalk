---
type: issue
status: backlog
tags: [grading]
kind: defect
created: 2026-11-12
creator: claude
---

# chalk autograde --all apaga os ajustes manuais

Ao recorrigir (`chalk autograde <quiz>/<questão> --all`), o grade novo é gravado com `adjustments=None` (`chalk/cli/autograde_cmd.py`). Ajustes que o professor fez à mão (pontos dados, atraso, questão anulada) somem sem aviso.

Comportamento mantido na extração do `chalk-grader` (11ffe3b) para não mudar duas coisas de uma vez.

Decidir:

- preservar os ajustes existentes e aplicar sobre a nova nota (provável), ou
- manter o comportamento e avisar quantos ajustes serão apagados, com confirmação.
