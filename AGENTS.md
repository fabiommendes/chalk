# chalk

CLI para corrigir quizzes e manter roster e notas em arquivos de texto. Ver
`README.md` para o layout de uma turma e os formatos.

## Idioma

Nível 2 (`~/git/tools/tooling-root/dev/adr/0002-idioma-dos-repositorios.md`):
código, comentários, `README.md`, `docs/` (inclusive `docs/user-stories/`)
e `GLOSSARY.md` em inglês; `AGENTS.md` e tudo em `dev/` em português.

## Verificação

```sh
r2 check                          # = uv run task check: ruff, pytest e mkdocs --strict
uv run pytest tests/test_x.py -k nome   # um teste
uv run ruff format                # formatar
```

Rode antes de cada commit. Testes ficam em `tests/` e usam a turma de exemplo
`tests/examples/turma` (fixture `classroom` em `tests/conftest.py`, que copia
a turma para um diretório temporário). `tests/test_cli_smoke.py` roda todo
comando não interativo; comando novo entra na lista.

Os testes com `bwrap` (sandbox do motor) são pulados dentro do sandbox do
Claude Code ("bwrap cannot create a sandbox here"). Quem mexe no motor roda
`uv run pytest packages/chalk-grader/tests` fora dele.

## Pacotes

Workspace uv com dois pacotes:

- `chalk` (raiz): quizzes, roster, notas, CLI.
- `chalk-grader` (`packages/chalk-grader/`, `import chalk_grader`): o motor de
  correção (perfis, sandbox, `ProfileGrader`, scoring, guard). Dependência
  comum do chalk e do `chalk-worker`. Não importa nada do chalk; testes em
  `packages/chalk-grader/tests/`, sem a turma de exemplo.

O chalk passa a questão para o motor como `chalk_grader.task.Task`
(`BaseQuestion.get_task`). `Score`, `Graded`, os motivos simples de
desclassificação e os modelos `Autograder`/`Profile`/`Limits`/`Service` são
do motor; `chalk.core.score`, `chalk.core.grader`,
`chalk.core.disqualification` e `chalk.core.models` os reexportam.

## Dependências irmãs

- `mdq` vem do checkout local `../../codehood/mdq/mdq-py` (`[tool.uv.sources]`
  em `pyproject.toml`). A versão do PyPI está atrás. Não mudamos o mdq por
  causa do chalk: o chalk segue as regras dele (por exemplo, `stem`
  obrigatório).
- `optionz` (`import opt`) e `errorz` vêm do PyPI. `opt.unpack` não existe
  lá; use `chalk.util.unpack`.

## Convivência com o codehood

Uma turma pode ser ao mesmo tempo projeto chalk e curso codehood. Regras em
`dev/adr/0001-questoes-em-mdq-e-roster-compartilhado-com-o-codehood.md`:

- O chalk lê `codehood.toml`, `questions/`, `exams/` e `graders/` do curso e
  fala com a REST do codehood, só para `chalk codehood autograde` (chave `BOT`
  em `CODEHOOD_BOT_KEY` ou `--key-file`; a chave nunca entra no sandbox).
  Fora isso, ele só toca o `roster.csv` (esquema compartilhado) e as colunas
  de quiz do `grades.csv` (`chalk codehood grades`).
- Ao salvar `roster.csv`, preserve colunas desconhecidas, a ordem das colunas
  e as linhas sem id.
- Com `codehood.toml` na raiz da turma, `chalk init` acrescenta `chalk.toml` ao
  `.codehoodignore` do curso, e `chalk quiz create ID` acrescenta `ID/`. Sem
  `codehood.toml`, não toca nele.

## Armadilhas conhecidas

- Importar `chalk.data` antes de `chalk.core` gera import circular. Importe
  `chalk.core` primeiro.
- `chalk.cli.util.safe` converte exceções em mensagem e sai com código 1.
  Use `CHALK_DEBUG=1` para ver o traceback.
