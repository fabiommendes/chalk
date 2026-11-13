---
type: issue
status: completed
tags: [cli]
kind: defect
created: 2026-11-12
creator: claude
---

# Pequenos defeitos de saída: help do `--server` e `type: null`

- `chalk codehood autograde --help` mostra `Server URL. Default:  url.`: o rich interpreta `[server]` como markup (`chalk/cli/codehood_app.py:63`). Escapar como `\[server]`.
- `chalk quiz create p1 --questions 5` grava `type: null` em cada questão do `conf.yaml`. Omitir o campo quando não há tipo.
