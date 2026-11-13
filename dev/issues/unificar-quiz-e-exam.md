---
type: issue
status: open
tags: [cli, codehood]
kind: feature
created: 2026-11-13
creator: claude
---

# Unificar quiz e exam

O chalk e o Codehood usam dois conceitos para a mesma coisa. Para o chalk, um
quiz é um diretório na raiz da turma (`chalk/core/quiz.py`, exceto os nomes
de `QUIZ_IGNORE_LIST`). Para o Codehood, um exam é um arquivo
`exams/<slug>.md` que inclui questões de `questions/` pelo id. Num repositório
de curso do Codehood, como `~/git/aulas/paradigmas-ch`, o chalk não enxerga
nenhuma das provas e listas:

```
$ chalk show lista-elm-prolog
Error: Quiz 'lista-elm-prolog' does not exist! (quiz = 'lista-elm-prolog')
$ chalk show
Error: "None of [Index(['name', 'start', 'end', 'questions'], dtype='str')] are in the [columns]"
```

Só `chalk codehood autograde` sabe ler um exam. Os outros comandos (`show`,
`grade`, `autograde`, `extract`) exigem o layout de quiz.

Não há motivo para manter os dois. Proposta: o chalk passa a tratar um
`exams/<slug>.md` como quiz, com as questões resolvidas pelos `include:` e os
graders encontrados como no `chalk codehood autograde`. Falta decidir se o
layout de diretório continua aceito ou se migramos os cursos antigos.

O segundo erro acima, o do `chalk show` sem argumento, é um defeito à parte:
uma turma sem quizzes deveria mostrar uma tabela vazia, não um erro do
pandas.
