---
type: issue
status: backlog
kind: task
priority: low
created: 2026-11-12
creator: claude
---

# Escrita em stream não distingue texto de bytes

`chalk/data/__init__.py:64` escreve `source` em qualquer objeto com `write`, sem saber se é `IO[str]` ou `IO[bytes]` (TODO no código, com `# type: ignore`). Um `bytes` num stream de texto falha só em tempo de execução.

Opções: checar `isinstance(dest, io.TextIOBase)` / `io.RawIOBase | io.BufferedIOBase`, ou converter com base no tipo de `source` e no `mode` do stream quando houver.
