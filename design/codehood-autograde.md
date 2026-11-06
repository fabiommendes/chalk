# Corrigir respostas do codehood com o autograder do chalk

Estado em 2026-11-05. Rascunho. A parte do servidor está no codehood, em
`dev/specs/to-do/runner-de-correcao.md`.

## Problema

No codehood, as questões de código (`[essay]` com `content: code`) só têm
correção manual. Na Prova 1 de Paradigmas são 155 respostas de Prolog numa
questão só. O servidor do codehood não executa código de aluno, e o chalk já
tem o motor: perfis, sandbox `bwrap`, nota pela lista de testes da solução,
guard e notas de suspeita (`design/sandbox.md`). Falta o caminho entre os
dois.

## Mudança na regra de convivência

`AGENTS.md` e `design/mdq-e-roster.md` dizem que o chalk só toca o
`roster.csv` e o `grades.csv` do codehood. Esta proposta amplia a regra: o
comando `chalk codehood autograde` também lê `codehood.toml`, `questions/`,
`exams/` e `graders/` do curso, e fala com a REST do codehood. Os quizzes
do chalk (pastas com `conf.yaml`) não mudam.

## Layout

```
turma/
├── codehood.toml
├── chalk.toml                  # perfis próprios do professor, se houver
├── questions/logico/aritmetica/fatorial-com-is.md   # id: prolog-fatorial-com-is
└── graders/logico/aritmetica/fatorial-com-is/
    ├── grader.yaml             # o bloco `autograder:` de uma questão do conf.yaml
    ├── template/               # testes e arquivos confiáveis
    │   └── tests.pl
    └── solution/               # solução de referência (arquivo ou pasta)
        └── answer.pl
```

- O grader de `questions/<caminho>/<nome>.md` é `graders/<caminho>/<nome>/`.
  O slug do servidor é o `id` do frontmatter da questão. Pasta de grader sem
  questão é erro.
- `grader.yaml` usa o modelo `Autograder` (`profile`, `answer`, `timeout`,
  `limits`, `vars`, `suspicious`...). Sem `profile`, o padrão vem do
  `highlight` da questão (`prolog` → `prolog-plunit`, `elm` → `elm-test`,
  `python` → `python-pytest`).
- Os perfis do `chalk.toml` da turma valem aqui também.

## Comando

```
chalk codehood autograde --exam <slug> [--question <slug>] [--dry-run]
                         [--server <url>] [--key-file <arquivo>]
```

1. Servidor em `[server] url` do `codehood.toml`; chave `BOT` em
   `CODEHOOD_BOT_KEY` ou `--key-file`. A chave nunca entra no sandbox.
2. Lê a prova, cruza as questões com os graders e roda o `prepare` de cada
   grader (cache, lista de testes pela solução). Uma solução que não tira
   nota máxima aborta a questão antes de corrigir a turma.
3. Lista as submissões `PENDING_GRADE` e `GRADED_AUTOMATICALLY` da questão,
   fica com a mais nova por tentativa, só de tentativas fechadas, e pula a
   que já tem feedback humano.
4. Corrige cada resposta com o `ProfileGrader` (resposta em texto, gravada
   em `answer`).
5. Grava `PUT .../submission/<publicId>/feedback` com `ref` = nome do bot,
   `score` (fração), `feedback` (linha por teste, ✓ ou ✗, em português) e
   `notes` (padrões suspeitos, recusas do guard, log do build-error).
   Rodar de novo atualiza o mesmo passe.
6. Erro de infraestrutura (sandbox, perfil, `prepare`) não grava nada e vai
   para o relatório. `Timeout` e `build-error` gravam 0 com a mensagem.
7. `--dry-run` não grava e imprime a distribuição das notas.
8. Relatório no terminal: por questão, corrigidas, puladas por nota humana,
   erros, distribuição e quantas com notas de suspeita.

`chalk codehood autograde --check <grader>` roda só o passo 2.
`chalk codehood autograde --try <grader> <arquivo>` corrige um arquivo local,
sem servidor.

## Perfil `prolog-plunit`

- `swipl` achado por probe; testes `plunit` do `template/`, relatório JUnit
  escrito por um runner próprio em `{runners}` (o plunit não gera JUnit).
- Um processo `swipl` por teste, com timeout por teste, para que laço
  infinito e `halt/0` derrubem só o teste.
- Antes de rodar, o runner carrega as cláusulas do aluno num módulo
  temporário e confere cada corpo e diretiva com `safe_goal/1` da
  `library(sandbox)` (a do SWISH). Programa inseguro (`halt`, E/S,
  `assert` em módulo do sistema, `initialization`...) não roda: vira
  `build-error` com a lista do que foi recusado, e entra nas notas.
  Conferido no SWI-Prolog 10: `:- initialization(halt(0))` é recusado; um
  corpo que chama predicado do próprio aluno precisa das cláusulas já
  carregadas no módulo para passar.
- `vars.safe = "on"` por padrão; `off` para questões que precisam de E/S.

## Perguntas abertas

- Q1. Notas de suspeita entre alunos (cola) entram aqui ou num comando
  próprio? O `~/git/plagiarism` existe.
- Q2. O cliente REST fica em `chalk/codehood.py` ou num módulo novo
  `chalk/codehood/`?
