---
type: issue
status: backlog
tags: [autograder, chalk-grader, elm]
kind: defect
created: 2026-11-13
creator: claude
---

# Feedback de erro de compilação leva ruído para o aluno

Com `on_build_error: zero` no perfil `elm-test`, o feedback gravado para o aluno começa com as linhas de progresso do `elm-test` (`Verifying dependencies (0/8)` ... `Dependencies ready!`, `Compiling ...`) e mostra o caminho do diretório temporário (`/tmp/chalk-s1-.../src/Main.elm`).

Proposta: no chalk-grader, filtrar do feedback as linhas de progresso conhecidas do perfil e trocar o caminho do workdir por um caminho relativo (`src/Main.elm`). Pode ser um campo do perfil (`build_output_filter`) ou um tratamento só do `elm-test`.
