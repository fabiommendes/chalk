---
type: adr
status: accepted
tags: [grading, score]
created: 2026-11-12
decided: 2026-11-12
creator: claude
---

# Notas como números exatos

## Contexto

Notas são somadas, multiplicadas por pesos e ajustadas, e frações como 1/3 aparecem em correção proporcional (2 de 3 testes).

Evidência: `packages/chalk-grader/chalk_grader/score.py:1-3` ("Scores: exact numbers, usually in [0, 1], as Decimal or Fraction."); `THIRD_SCORE` e `TWO_THIRDS_SCORE` como `Fraction` em `score.py`; o tipo vem de 8e80cba (2026-07-17).

## Decisão

`Score` é `Decimal` ou `Fraction`, nunca `float`. Motivo não registrado.

## Consequências

- Somas e pesos não acumulam erro de arredondamento, e 1/3 + 2/3 dá 1.
- Todo valor que entra (CSV, YAML, relatório do script) passa por `to_decimal` ou equivalente.
