---
type: note
status: open
kind: design
tags: [grading, cli, mdq, codehood]
relatedTo:
  - dev/issues/autograde-aborta-na-primeira-resposta-invalida.md
  - dev/issues/erro-de-correcao-mostra-repr-da-issue.md
  - dev/issues/grader-do-codehood-nao-usado-em-quiz-com-source.md
created: 2026-11-12
creator: claude
---

# Design: correções da convivência com o codehood (B1, B2, B4)

B1 e B2 saem juntos (tarefa T1). B4 é independente (tarefa T2) e pode rodar em
paralelo: os arquivos se tocam só em `chalk/question/mdq.py`, em métodos
diferentes (T1: `validate_answer`, `to_response`, `grade_answer`; T2:
`get_grader`, `get_reference_answer`, método novo). Quem fizer o merge por
último resolve o conflito textual, se houver.

## B1. Resposta inválida não aborta `chalk autograde`

### Classificação das respostas mdq

O mdq só tem `ResponseError` para os dois casos, sem subclasse. Distinguir
pela mensagem é frágil. Então o chalk mesmo faz a checagem de referência
antes de chamar o mdq, e todo `ResponseError` que sobra é tratado como fora
do domínio.

| Caso | Exemplo | Quem detecta | Resultado |
|---|---|---|---|
| Referência inexistente | `b` numa múltipla escolha sem `b`; chave de statement/blank inexistente | chalk, em `MdqQuestion.to_response` | sem nota, aviso, `ValueError(Issue)` com code `unknown-choice` |
| Fora do domínio | `3.5` em `integer`; texto em `numeric`; formato errado | mdq (`ResponseError`) em `grade_answer` | `Graded(0, feedback=...)`, gravado no `grades.csv` |
| Vazia | `"  "` | `empty_result()` (já existe) | sem nota, aviso |

Decisão sobre referência inexistente: **sem nota, com aviso**. Motivo: um id
que não existe quase sempre é erro de importação ou mapeamento (letra do
formulário vs. id do mdq), não escolha do aluno; e uma nota 0 gravada fica
"already graded" e esconde o erro nas próximas execuções.

### Mudanças em `chalk/question/mdq.py`

- `to_response`: depois de converter, chama `self._check_references(response)`.
- Novo método privado:

  ```python
  def _check_references(self, response: Any, /) -> None:
      """
      Raise ValueError(Issue) with code "unknown-choice" when the response
      refers to a choice, statement or blank the document does not have.

      multiple-choice: the id; multiple-selection: each id; true-false:
      the keys of the mapping (statement ids, in document.choices);
      fill-in: the keys of the mapping (document.blanks[*].id). Other types
      and responses of the wrong shape pass (mdq rejects the shape later).
      """
  ```

  Mensagem: `f"Answer {value!r} is not one of the choices: {', '.join(ids)}"`
  (para blank: `"... is not a blank of the question: ..."`). Severidade
  `ERROR`, escopo `response`.
- `validate_answer`: passa a ser só `return self.to_response(answer)`. Não
  chama mais `score_response`. Resposta fora do domínio é válida (é uma
  resposta errada), então `persist_answer`, `render_answer` e o cache de
  `submissions.py` a aceitam.
- `grade_answer`: em `ResponseError`, retorna
  `Graded(Decimal(0), feedback=f"Invalid answer, graded as wrong: {e}")` em
  vez de levantar. `NotAutoGradable` continua retornando `None`.
- Remover o uso do code `invalid-response` (não sobra nenhum).

Fica sem mudar: valor de choice inexistente dentro de um blank de fill-in
(`Response id ... not found in blank`) vem do mdq como `ResponseError` e vira
nota 0. Aceitável: é raro e não vale descer na estrutura do blank.

### Mudanças em `chalk/cli/autograde_cmd.py:run_autograder`

```python
invalid: list[StudentId] = []
...
try:
    ans: Any = question.validate_answer(answer)
    graded = grader(student.id, ans, **grader_kwargs)
except ValueError as e:
    rich.print(Text(f"invalid answer: {error_message(e)}", style="red"))
    invalid.append(student.id)
    continue
...
# depois do laço (os saves já acontecem dentro dele):
if invalid:
    rich.print(
        Text(f"{len(invalid)} answer(s) not graded: {', '.join(invalid)}", style="red"),
        file=sys.stderr,
    )
    raise typer.Exit(1)
```

- Só `ValueError` é capturado. Outras exceções (sandbox, `PrepareError`)
  continuam abortando: são problema do ambiente, não do aluno.
- Nada é gravado no `grades.csv` para a resposta inválida (nem feedback):
  `grades.set_score` exige nota, e deixar vazio faz a próxima execução tentar
  de novo depois que o professor corrigir o dado.
- Use `Text(...)`, não markup: a resposta do aluno pode ter `[...]`.
- `--dry-run` também sai com 1 se houver inválidas.
- Saída final: código **1** se houve resposta inválida, 0 caso contrário.
  Resposta fora do domínio (nota 0) não conta como inválida.
- `run_autograder_debug` (`--run`) fica como está (é interativo e mostra o erro).

### Testes (T1)

`tests/test_mdq_question.py`:
- `validate_answer("xx")` em q1 levanta `ValueError` cujo `args[0]` é `Issue`
  com `code == "unknown-choice"` (ajusta o teste atual).
- `validate_answer("dois, xx")` em q2 levanta `unknown-choice`.
- questão `numeric` com `domain: integer` (criar arquivo no teste):
  `validate_answer("3.5")` não levanta; `grade_answer("3.5")` dá
  `Graded(0, feedback contendo "not an integer")`.
- true-false com chave inexistente levanta `unknown-choice`.

`tests/test_autograder_chalk.py` (ou novo `tests/test_autograde_invalid.py`),
com a fixture `classroom`, via `CliRunner` em `chalk autograde p1/q1`:
- `submissions.csv` com `0001` = `xx` e `0002` = `df`: código de saída 1,
  saída contém `invalid answer: Answer 'xx' is not one of the choices`, não
  contém `Issue(`; `grades.csv` tem nota para `0002` e nada para `0001`.
- numérica inteira com `3.5` e `3`: código 0, as duas com nota (0 e 1), a
  primeira com o feedback.

## B2. Erro mostra o `repr` da `Issue`

### Mudanças em `chalk/core/issue.py`

- `Issue.__str__`: `return self.message or self.code`. Assim
  `str(ValueError(issue))` já sai legível.
- Nova função pública (entra em `__all__` se o módulo tiver):

  ```python
  def error_message(exc: BaseException, /) -> str:
      """
      Human readable message of an exception. Unwraps ValueError(Issue) and
      ValueError([Issue, ...]) into the messages of the issues, joined by
      "; ". Any other exception gives str(exc).
      """
  ```

- `list_of_issues`: já desempacota `ValueError(Issue)` (via `args`, ramo
  `Iterable`). Corrigir só a ordem: o ramo `Mapping` está depois de
  `Iterable` e nunca roda; mover para antes.

### Quem passa a usar `error_message`

- `chalk/cli/util.py:safe`: imprime `Text.assemble(("Error: ", "b red"), error_message(e))`.
  Além disso, deixar passar `typer.Exit` e `typer.Abort` sem tocar
  (`except (typer.Exit, typer.Abort): raise` antes do `except Exception`).
  Hoje `typer.Exit(1)` de `check_autograder` é capturado e vira
  `Error: 1`, bug achado no caminho.
- `chalk/question/__init__.py:render_answer`: `str(e)` vira `error_message(e)`.
- `chalk/cli/autograde_cmd.py`: o laço de B1.

### Testes (T1)

`tests/test_utilities.py` (ou novo `tests/test_issue.py`):
- `error_message(ValueError(Issue.error("x", "msg")))` == `"msg"`.
- `error_message(ValueError([Issue.error("a", "m1"), Issue.warning("b", "m2")]))` == `"m1; m2"`.
- `error_message(ValueError("plain"))` == `"plain"`; `str(Issue.error("code"))` == `"code"`.
- `list_of_issues(ValueError(issue), ["response"]) == [issue]`.
- `list_of_issues({"1": "m"}, [], code="e")` dá uma issue com code `e1` (ramo Mapping).
- CLI: um comando com `typer.Exit(1)` dentro de `safe` não imprime `Error: 1`
  (`chalk autograde --check` numa questão cuja solução não tira nota cheia
  serve, se houver uma sem bwrap; senão, teste unitário de `safe`).

## B4. Quiz com `source:` usa o grader do codehood

### Onde resolver

Em `MdqQuestion.get_grader` (`chalk/question/mdq.py`). Ordem:

1. script `autograde.*` na pasta da questão do quiz (`get_autograde_script`),
   como hoje;
2. grader do curso codehood, se a questão vem de `questions/<path>.md` e
   existe `graders/<path>/grader.yaml`;
3. correção do mdq, como hoje.

O `autograder.profile` do `conf.yaml` continua ignorado pelas questões mdq
(comportamento atual; fora do escopo).

### Mudanças em `chalk/codehood_autograde.py`

```python
def find_course_root(path: Path, /) -> Path | None:
    """
    The nearest ancestor of path (path itself excluded) with a codehood.toml,
    or None. Does not read the file.
    """


def find_question_grader(question: Path, /) -> FoundGrader | None:
    """
    The grader of a question file of a codehood course: for
    <root>/questions/<path>.md, the one in <root>/graders/<path>/grader.yaml.

    None when the file is not under questions/ of a course or there is no
    grader.yaml. Does not scan the other graders, so a broken grader of
    another question does not get in the way.

    Raises:
        GraderLayoutError: the grader.yaml is invalid, the question has no
            `id`, or there is no profile (same rules as find_graders).
    """


def make_grader(
    found: FoundGrader,
    root: Path,
    *,
    quiz_id: str = "codehood",
    question_id: str | None = None,
) -> ProfileGrader:
    """
    The profile grader of a question. root is the course root: profiles come
    from its chalk.toml and the cache goes to <root>/.chalk/cache.
    question_id defaults to found.slug. Both ids only label the run.
    """
```

- O corpo do laço de `find_graders` vira um helper privado
  `_load_grader(root: Path, conf_path: Path) -> FoundGrader`, usado por
  `find_graders` e `find_question_grader`. As regras ficam iguais.
- `make_grader` hoje recebe `CourseConfig`, mas só usa `course.root`. Troca
  para `root: Path` (é API interna do módulo; três chamadas: `autograde_exam`,
  `run_check`, `run_try`). Assim o quiz não depende de `codehood.toml` ter
  `[course]` completo.
- Profiles vêm do `chalk.toml` da raiz do curso, igual a `chalk codehood
  autograde --check`. Assim os dois comandos dão a mesma nota. Normalmente a
  raiz do curso e a da turma são a mesma pasta.
- `find_course_root` compara caminhos resolvidos (`MdqQuestion.path` já vem
  resolvido de `Quiz`).

### Mudanças em `chalk/question/mdq.py`

```python
def find_course_grader(self) -> FoundGrader | None:
    """
    The codehood grader of this question, when its file comes from
    questions/<path>.md of a codehood course and graders/<path>/grader.yaml
    exists. None for questions without a path.

    Raises:
        GraderLayoutError: see codehood_autograde.find_question_grader.
    """
```

`get_grader`, no passo 2:

```python
found = self.find_course_grader()
if found is not None:
    root = find_course_root(found.folder)  # nunca None aqui
    grader = make_grader(found, root, quiz_id=self.quiz.id, question_id=self.id)
    return _code_answer(grader)
```

- `_code_answer(grader)` (função privada do módulo) devolve um `Grader` que
  aplica `extract_code` em respostas `str` antes de chamar o `ProfileGrader`
  e repassa os kwargs (`timeout`, `keep_files`, `keep_failed`). `Path` passa
  direto. É o que `chalk codehood autograde` faz com a resposta
  (`codehood_autograde.grade_answer`); sem isso uma resposta com cerca
  Markdown daria nota diferente nos dois comandos.
- `get_reference_answer` (override em `MdqQuestion`): resposta do
  `answer_key.*` do quiz, se houver; senão `ProfileGrader.solution` do grader
  do curso; senão `None`. Faz `chalk autograde --check p1/fatorial` usar o
  `solution/` do curso.
- Imports de `chalk.codehood_autograde` ficam dentro dos métodos (o padrão de
  `base.py`), para não criar ciclo `question -> codehood_autograde -> core`.
- `Task` montada por `make_grader`: `question_id=self.id` (id do quiz),
  `quiz_id=self.quiz.id`, `root=graders/<path>/`, `template=graders/<path>/template`
  se existir. `root` precisa ser a pasta do grader porque mounts e o script
  de scoring do `grader.yaml` são relativos a ela.

### Motor (`chalk_grader`)

Não muda. Recebe um `ProfileGrader` comum, com `Task` e `Autograder` já
montados pelo chalk, como em `chalk codehood autograde`.

### Testes (T2)

Novo `tests/test_quiz_codehood_grader.py`, com a fixture `classroom` e os
helpers de `tests/test_codehood_autograde.py` (`add_question`, `write`; mover
para `tests/conftest.py` ou importar do módulo):

Sem executar o grader (rodam no sandbox):
- `find_question_grader`: acha `graders/logico/aritmetica/fatorial-com-is/`
  para `questions/logico/aritmetica/fatorial-com-is.md`; `None` sem
  `grader.yaml`; `None` sem `codehood.toml` acima; `None` para arquivo fora
  de `questions/`; `GraderLayoutError` com `grader.yaml` inválido.
- `find_question_grader` não falha quando outro grader do curso está quebrado.
- quiz `p1` com entrada `- id: fat` + `source: ../questions/logico/aritmetica/fatorial-com-is.md`
  e `codehood.toml` na raiz da turma: `question.find_course_grader().folder`
  é a pasta do grader; `get_grader()` não é `None`.
- com `p1/fat/autograde.py` presente, `get_grader()` é `ScriptGrader` (o
  script do quiz tem prioridade).
- `get_reference_answer()` devolve o texto de `solution/answer.pl`.
- `make_grader(found, root, quiz_id="p1", question_id="fat").task` tem os
  ids, `root` e `template` esperados.

Executando (marca `needs_swipl`; o `GRADER_YAML` dos testes usa
`sandbox: none`, então não depende de bwrap):
- `chalk autograde p1/fat` com submissões `CORRECT` e `WRONG`: notas 1 e
  menor que 1 no `grades.csv`; nenhuma linha `not graded.`.
- resposta `CORRECT` dentro de cerca ```` ```prolog ```` dá nota 1.
- `chalk autograde p1/fat --check` sai com 0.

Os testes de `tests/test_codehood_autograde.py` que chamam `make_grader`
indiretamente continuam passando (só muda o segundo argumento).

## Riscos

- B1: `validate_answer` deixa de rejeitar respostas fora do domínio. Quem
  dependia disso para filtrar dados (`persist_answer`, cache de
  `submissions.py`) passa a aceitar `3.5`. É o comportamento desejado, mas
  muda `chalk show`/`render_answer` para essas respostas.
- B1: notas negativas do mdq (`symmetric`) continuam para escolhas erradas
  válidas; só a resposta fora do domínio ganha 0. Pode parecer
  inconsistente ao professor.
- B1: um `ValueError` vindo de dentro de um script grader (bug do grader)
  agora vira "invalid answer" do aluno em vez de abortar. Mensagem mostra a
  causa; código de saída 1 avisa.
- B4: `find_course_root` sobe até a raiz do sistema de arquivos; um
  `codehood.toml` perdido num diretório acima da turma (ex.: em `~`) faria o
  chalk procurar `graders/` lá. Só acontece se o arquivo da questão estiver
  num `questions/` daquela raiz, então o risco é baixo.
- B4: `make_grader` muda de assinatura. É função interna, mas está em
  `__all__`.
- Conflito textual entre T1 e T2 em `chalk/question/mdq.py`.
