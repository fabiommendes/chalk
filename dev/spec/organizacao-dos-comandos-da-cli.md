---
type: spec
status: active
tags: [cli]
created: 2026-11-12
creator: claude
---

# Organização dos comandos da CLI

Reorganização da CLI, implementada em 2026-11-12 (d9c1622, 4b5e39c,
35e9d7a). Substituiu `design/commands.md` (removido), que descrevia uma árvore que nunca
foi implementada.

## Problema

A CLI cresceu com dois estilos. `chalk show` recebe um `LOC` e muda de nível
(turma, quiz, questão) e de visão (`-g`, `-a ID`) por flags. Outros comandos
repetem partes dele em grupos (`quiz list`, `question list`,
`question show`, `info -c`, `collect`). Além disso:

- O quiz e a questão são passados de três jeitos: `LOC` (`p1/q1`), dois
  argumentos (`autograde p1 q1`, `question show p1 q1`) ou flag
  (`roster validate --quiz p1`).
- A mesma letra curta tem sentidos diferentes: `-f` é format, force ou
  fields; `-a` é all, answer ou quiz; `-g` é grades, autograder ou github.
- Há flags repetidas: `grade --force` e `--all`; `autograde --run`,
  `--run-script` e `--dry-run`.

## Duplicatas verificadas

Conferido no código e rodando na turma `tests/examples/turma`.

| Comando              | Equivalente em `show`  | Observação                                                         |
|----------------------|------------------------|--------------------------------------------------------------------|
| `question show Q P`  | `show Q/P`             | Não imprime nada (`render()` sem print) e ignora `-g`.             |
| `question list Q`    | `show Q`               | `show Q` já mostra a mesma tabela com notas e taxa de omissão.     |
| `quiz list`          | `show` (turma)         | `show` sem `LOC` imprime o `repr` do `Classroom`. Falta essa visão. |
| `info -c`            | `info`                 | A flag não muda nada: o padrão já é a turma.                       |
| `collect LOC`        | nenhum                 | Só leitura, exporta as respostas. Cabe em `show LOC --answers`.     |
| `roster show`        | nenhum                 | Só leitura. Cabe em `show --roster`.                               |

## Regras

1. Leitura vai em `chalk show [LOC]`. Comando de leitura em grupo não existe.
2. Escrita é um verbo de topo que recebe `LOC` (`grade`, `autograde`,
   `extract`, `clear`) ou um subcomando de um grupo de recurso (`roster add`,
   `quiz create`, `codehood grades`).
3. Quiz e questão sempre como `LOC` posicional: `p1` ou `p1/q1`. Quando um
   comando que não trata de quiz precisa de um, usa `--quiz QUIZ`. O termo é
   sempre quiz, nunca assignment.
4. Letras curtas reservadas, com um só sentido em toda a CLI:

   | Letra | Flag          |
   |-------|---------------|
   | `-f`  | `--format`    |
   | `-o`  | `--output`    |
   | `-s`  | `--sort`      |
   | `-a`  | `--all`       |
   | `-v`  | `--verbose`   |
   | `-y`  | `--yes`       |
   | `-n`  | `--dry-run`   |

   Outra letra só existe se nenhum outro comando usar a mesma letra para
   outra coisa. Quando dois disputam, os dois ficam só com a forma longa.
5. Todo comando que produz tabela ou dados aceita `-f` e `-o`, com a mesma
   lista de formatos: `table` (padrão no terminal), `csv`, `json`, `yaml`.

## Árvore proposta

```text
chalk
├── init                 [-c CLASSROOM] [--teacher TEACHER]
├── show [LOC]           leitura de turma, quiz, questão, roster e respostas
├── grade LOC            correção manual
├── autograde LOC        correção automática
├── extract LOC          respostas entre submissions.csv e arquivos
├── clear                arquivos gerados
├── info                 versão e ambiente
├── roster
│   ├── add
│   ├── import
│   └── validate
├── quiz
│   └── create
├── codehood
│   ├── grades
│   └── autograde EXAM[/QUESTION]
└── contrib [MODULE]
```

Saem: `quiz list`, `question list`, `question show`, `collect`,
`roster show`, `info -c`. Sem alias de compatibilidade.

## `chalk show`

| `LOC`   | Sem flag                                  | `-g`                     | Outras                                               |
|---------|-------------------------------------------|--------------------------|------------------------------------------------------|
| vazio   | resumo da turma e tabela de quizzes       | notas de todos os quizzes | `--roster`: tabela do roster                         |
| `p1`    | tabela de questões                        | notas do quiz            |                                                      |
| `p1/q1` | enunciado e metadados                     | notas da questão         | `--answers`: todas as respostas; `--student ID`: uma |

Flags comuns: `-f`, `-o`, `-s`, `--color`, `--total/--no-total`, `--final`.

- `--student ID` substitui `-a ID` (a letra `-a` fica para `--all`). Com
  `--answers` ou sozinho, mostra a resposta do aluno; com `-g`, a nota dele.
- `--answers` herda os formatos do `collect` (`yaml`, `json`, `csv`, `md`).
  O padrão passa a ser `md`, mais legível no terminal.
- `--roster` herda o `-s` do `roster show` (`id`, `name`, `email`, `github`,
  com prefixo `-` para ordem decrescente).
- `-f json` ou `-f yaml` sem `LOC` produz a estrutura que hoje sai de
  `chalk info`.

## Outros comandos

- `info`: mostra versão do chalk e das dependências. `--debug` acrescenta
  caminhos e variáveis de ambiente (chaves e tokens aparecem só como
  `<set>`). Saem `-c` e `--version`, que repetia o padrão.
- `autograde LOC`: troca `QUIZ [QUESTION]` por `LOC`.
  - `--run` e `--run-script` viram um só `--run`: roda o script, mostra a
    saída e não salva nada. A saída é capturada e impressa linha a linha,
    como no antigo `-r`; o modo sem captura sai, porque a nota depende da
    captura.
  - `--dry-run` passa a `-n`.
  - `--timeout`, `--keep-files` e `--keep-failed` ficam só na forma longa.
  - Corrigir a ajuda de `--limit`: limita o número de alunos, não há lote.
- `grade LOC`: sai `--force`, que não é usado; fica `-a/--all`.
- `extract LOC`: `--force` e `--ext` só na forma longa.
- `clear`: sem opções. Apaga o cache dos perfis (`.chalk/cache`); antes só
  imprimia pastas `tmp-*` que nada cria, e `--all` e `--autograder` faziam
  a mesma coisa. Uma opção volta quando houver outra coisa a apagar. Roster, quizzes, submissões e notas nunca saem. Os
  arquivos de `--keep-files` ficam no tmp do sistema, sem separação por
  turma, e não são apagados.
- `roster add`: `--name`, `--email` e `--github` só na forma longa (`-n`,
  `-e` e `-g` estão reservados ou disputados).
- `roster import`: `-r/--replace` fica; `--keep` só na forma longa.
- `roster validate`: `--fields` e `--quiz` só na forma longa; `--yes/--no`
  vira `-y/--yes` e `--no`.
- `quiz create`: `--name` só na forma longa; `-q/--questions` fica.
- `init`: `-c/--classroom` fica; `--teacher` só na forma longa (disputa `-t`
  com `autograde --timeout`).
- `codehood autograde`: troca `--exam SLUG [--question SLUG]` por
  `EXAM[/QUESTION]` posicional, como o `LOC` dos quizzes. Os slugs são o
  `id` do frontmatter e não têm `/`. `exam` fica: é o termo do codehood, não
  um quiz do chalk. `--dry-run` passa a `-n`. `--check GRADER` e
  `--try GRADER FILE` seguem como modos que dispensam o posicional.
- `contrib --help` quebrava (`module 'chalk.contrib.__help' not found`);
  agora mostra a ajuda e a lista de módulos.

## Documentação gerada

A referência de comandos sai do próprio código, para não divergir:

- `typer chalk.cli utils docs --name chalk` gera Markdown com todos os
  comandos e flags. O arquivo fica em `docs/user-manual/cli.md`, versionado,
  no menu do MkDocs como "Command reference". `uv run task cli-docs` regera, e
  `tests/test_cli_docs.py` falha se o arquivo não bater com a saída do
  comando.
- Sem man pages. O `click-man` não acha o comando porque o Typer 0.26 embute a
  própria cópia do click (`typer._click`), e um gerador nosso dependeria dessa
  API privada. O `--help` e a página do manual cobrem o uso.
- Os módulos de `contrib` são carregados sob demanda e não entram na
  referência. `chalk contrib` sem argumento continua listando os módulos.
