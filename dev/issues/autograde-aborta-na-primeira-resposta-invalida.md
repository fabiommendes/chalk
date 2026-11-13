---
type: issue
status: completed
tags: [grading, cli, mdq]
kind: defect
created: 2026-11-12
creator: claude
---

# `chalk autograde` aborta na primeira resposta inválida

Visto no teste de convivência com o codehood (`~/aulas/paradigmas/ch`).

Em `chalk/cli/autograde_cmd.py:374`, `question.validate_answer(answer)` levanta `ValueError(Issue)` quando a resposta não é válida para a questão mdq (id de escolha inexistente, `3.5` numa questão de domínio inteiro). A exceção sobe até `chalk.cli.util.safe`, que sai com código 1. Os alunos seguintes não são corrigidos.

Reprodução: quiz com uma questão de múltipla escolha e duas linhas em `submissions.csv`, a primeira com `a` (id inexistente) e a segunda com um id válido. `chalk autograde quiz/q` mostra o erro do primeiro aluno e para; o segundo fica sem nota.

Comportamento desejado: registrar o problema do aluno (na saída e, talvez, na linha `feedback` do `grades.csv`) e seguir para o próximo. O código de saída pode continuar diferente de zero quando houve resposta inválida.

Decidir junto: resposta fora do domínio (`3.5` onde se pede inteiro) é resposta errada (nota 0) ou inválida (sem nota)? Hoje vira erro, o que deixa o aluno sem nota mesmo depois da correção acima.
