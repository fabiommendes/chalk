---
type: issue
status: backlog
tags: [codehood, autograder]
kind: defect
created: 2026-11-13
creator: claude
---

# `extract_code` não trata cerca de código sem fechamento

Visto na correção da prova `lista1-elm` (curso paradigmas). `chalk/codehood_autograde.py:extract_code` só extrai blocos cercados fechados. Respostas reais chegam com ` ```elm ` sem fechamento, com ` ``elm ` (duas crases) ou com lixo depois da cerca (` ```[cite: 8] `). A cerca fica no código e o build quebra, e o aluno tira 0 por formatação.

O curso contornou isso com um script no perfil `elm-answer` (`chalk.toml` do curso), que apaga linhas que começam com duas ou mais crases.

Proposta: em `extract_code`, aceitar uma cerca de abertura sem fechamento (tudo depois dela é código) e descartar linhas que são só crases, com ou sem rótulo. Testes com os três formatos acima.
