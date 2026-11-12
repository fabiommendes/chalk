---
type: issue
status: backlog
tags: [cli]
kind: task
priority: low
created: 2026-11-12
creator: claude
---

# Arquivos ocultos em chalk show detectados só pelo ponto inicial

`chalk/util/show.py:128` (`_show_file`) esconde um arquivo quando o nome começa com `.`. O FIXME diz que não funciona no Windows, onde oculto é um atributo do arquivo.

O motor é só Linux (ADR 0005), mas o resto do chalk não tem essa restrição declarada. Decidir se o chalk inteiro é só Linux (e apagar o FIXME) ou tratar o atributo oculto.
