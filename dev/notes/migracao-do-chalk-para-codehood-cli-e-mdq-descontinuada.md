---
type: note
status: open
kind: pitch
tags: [codehood, mdq]
created: 2026-11-12
creator: claude
---

# Migração do chalk para codehood CLI e mdq (descontinuada)

> **Descontinuado.** Substituído por `dev/adr/0001-questoes-em-mdq-e-roster-compartilhado-com-o-codehood.md`. O plano abaixo
> propunha congelar o chalk e migrar tudo para o codehood. A decisão foi
> outra: chalk e codehood convivem no mesmo repositório da turma, e o chalk
> corrige o que acontece fora da plataforma. Fica aqui só como histórico.

Estado em 2026-10-29. Projetos comparados:

- chalk: `~/git/edu/chalk` (HEAD `23fb6bf`, 2026-07-17)
- codehood CLI: `~/git/codehood/codehood/cli`
- mdq: `~/git/codehood/mdq` (`mdq-py`, `mdq-js`)


## Resumo

- O chalk é 100% local: as submissões chegam de fora (CSV de Moodle,
  Forms ou GitHub Classroom) e a correção acontece em arquivos. No codehood,
  o servidor é a fonte de verdade das submissões e a CLI só faz push do
  material do curso. Essa é a divergência principal, e ela decide boa
  parte do plano.
- O chalk está em mau estado: 10 commits, nenhum teste útil (o único teste
  real nem importa), vários comandos com `NotImplementedError` e
  documentação descrevendo formatos antigos. Não vale portar código em
  bloco. Vale portar ideias e algumas peças isoladas, reescritas com
  testes sobre os modelos do mdq e do codehood.
- O que o chalk tem e os outros não têm: autograder por script, correção
  manual interativa, ajustes de nota (atraso, recorreção, override),
  desclassificações, gestão de roster e integração com GitHub Classroom.
- O que vai para o mdq é pouco: o tipo de questão "association"
  (matching, que já está no backlog do mdq) e talvez métodos extras de
  nota para multiple-selection. Autograder de código não entra no mdq
  (e-judge está listado como não objetivo no `BACKLOG.md`).


## O que o chalk tem a mais

| Recurso no chalk | Onde | Situação no codehood/mdq | Destino sugerido |
| --- | --- | --- | --- |
| Autograder por script (`template/`, repositório temporário, timeout, variáveis `CHALK_*`) | `chalk/autograder/`, `core/grader.py` | Glossário fala em "grading bot" (`ApiKey` do tipo BOT, `Feedback.botId`), sem código | CLI: `codehood autograde` funcionando como bot |
| Extração do resultado (JSON, relatório JSON do pytest, linha `CHALK_RESULT:`, resumo do pytest, elm-test) | `autograder/result_extractor.py`, `contrib/parser/elm_test` | nada | portar junto com o autograder, com testes |
| Correção manual em TUI com atalhos (`0 1 h q1 q3`, desfazer) | `cli/grade_cmd.py` | servidor tem `Submission.PENDING_GRADE` e `Feedback`; CLI não tem nada | CLI: `codehood grade` (Textual já é dependência) |
| Ajustes de nota (`late 0.8`, `regraded`, `=> 5`) | `core/adjustment.py` | `Feedback` só guarda score | servidor + CLI, se ainda fizer sentido |
| Desclassificação (timeout, erro, plágio) | `core/disqualification.py` | nada | parte vira status de `Feedback`, parte é descartada |
| Roster: import com merge, validação por regex, preenchimento de usuários do GitHub | `cli/roster_app.py`, `contrib/github/roster` | `roster.csv` é reconhecido pelo `file_tracker.py` mas ninguém lê; `codehood roster` está no ROADMAP 0.1 | CLI: `codehood roster` |
| GitHub Classroom (clone, link de repositórios por aluno) | `contrib/github/classroom` | codehood hospeda os próprios repositórios git | ver D2 |
| Nota final por script (`conf.py` com `final_grade(**totais)`) | `core/classroom.py:338` | `grades.py` com `grade(student) -> dict` | já existe no codehood; só alinhar |
| `collect`/`extract`: juntar ou espalhar respostas em arquivos por aluno | `cli/collect_cmd.py`, `cli/response_cmds.py` | nada | só se houver modo local (D1) |
| Transformações de texto (`strip`, `lower`, `unidecode`) | `builtin_scripts.py` | mdq já normaliza caixa, acentos e espaços no short-answer | descartar |
| Tipo `repo` (resposta é um diretório) | `question/repo.py` | nada no mdq | vira questão do autograder no codehood, não do mdq |
| Tipo `association` | `question/association.py` | backlog do mdq (matching) | mdq |
| Plágio | `cli/plagiarism_app.py` | nada | descartar (quebrado, dependência removida) |


## Pontos de divergência

1. **Fonte de verdade das submissões.** O chalk lê `<quiz>/submissions.csv`
   num formato largo (uma linha por aluno, uma coluna por questão). No
   codehood existe `Response` → `Submission` → `Feedback` no servidor, e a
   CLI não baixa nada disso.
2. **Formato das questões.** No chalk, questões são entradas YAML dentro
   do `conf.yaml` do quiz, em geral só a chave de resposta, sem enunciado
   (`choices: {a: 1, b: 0}`). No codehood/mdq cada questão é um arquivo
   Markdown completo. Converter chalk → mdq perde pouco, mas produz
   questões sem enunciado, que o mdq talvez nem aceite.
3. **Escala das notas.** chalk: `Decimal`/`Fraction` em [0, 1] vezes
   `value`. mdq: [-1, 1] com `weight`, e penalidade no nível do exame.
   codehood (`grades.ExamResult`): -100 a 100.
4. **Penalidade e métodos de nota.**
   - multiple-choice: chalk usa `penalty: fair|negative|<decimal>`; mdq usa
     `partial|symmetric`.
   - multiple-selection: chalk usa `sum|mean|min|all-or-nothing`; mdq usa
     `partial|all-or-nothing|symmetric`.
5. **Identidade do aluno.** chalk: `id` (matrícula) obrigatório, `github`
   e `email` opcionais, o resto em `extra`. codehood: `username`,
   `schoolId`, `githubId`, `email`; `grades.csv` aceita qualquer um deles
   como chave.
6. **Quiz e exame.** No chalk, um quiz é um diretório com `conf.yaml`
   (`start`, `end`, `weight`). No codehood é um exame mdq em `exams/`, com
   o tipo PRACTICE/QUIZ/EXAM e a agenda no servidor. A CLI ainda não faz
   push de exames (`dev/specs/to-do/push-exams.md`).
7. **Configuração.** `chalk.toml` (`[chalk] classroom, teacher, lang`)
   contra `codehood.toml` (`[course] discipline, instructor, edition`).
8. **Dependências.** As duas usam Python 3.13+, Typer, Rich e pydantic 2.
   chalk e mdq já compartilham `optionz`. O chalk traz pandas e outras
   dependências declaradas sem uso (pandera, toolz, cytoolz, typeguard),
   que não devem entrar no codehood.
9. **Divergências internas do próprio codehood** que a migração vai
   esbarrar: o layout de `exams/` é descrito de três formas diferentes
   (README, `file_tracker.py`, `docs/design/mapping-local-filesystem.md`),
   e o loader de includes do mdq não acha arquivos `.md` nem recursa.


## Plano sugerido

Cada fase é independente e pode virar uma spec em `dev/specs/to-do/` do
repositório de destino.

**Fase 0. Congelar o chalk.**
- Marcar o README como descontinuado e apontar para o codehood.
- Não corrigir bugs, exceto se forem necessários para exportar dados de
  turmas antigas.

**Fase 1. Roster no codehood (ROADMAP 0.1).**
- `codehood roster import|show|validate`, com merge por chave, validação
  por regex e coluna `github`.
- Definir o esquema de `roster.csv` com os campos do servidor (`username`,
  `name`, `email`, `school_id`, `github`).
- Desfaz a divergência 5.

**Fase 2. mdq.**
- Tipo matching (cobre o `association` do chalk).
- Avaliar se `mean`/`min` em multiple-selection são usados de verdade nas
  turmas antigas; se não, ficam de fora.
- Corrigir o loader de includes (pré-requisito do push de exames).

**Fase 3. Push de exames e leitura de submissões na CLI.**
- Implementar `push-exams.md`.
- `codehood pull` (ROADMAP 0.3) baixa respostas e notas para o diretório
  local, o que permite correção offline e `collect`.

**Fase 4. Autograder como grading bot.**
- `codehood autograde EXAM [QUESTION]`: busca submissões `PENDING_GRADE`,
  roda o script em diretório temporário com `template/` e timeout, e envia
  `Feedback` com `botId`.
- Portar `ScriptGrader` e `result_extractor` reescritos com testes; trocar
  o prefixo das variáveis de ambiente para `CODEHOOD_*`.
- Exige a questão de código no codehood (equivalente ao `repo` e ao `text`
  com `format` do chalk), que hoje não existe nem no mdq nem no servidor.

**Fase 5. Correção manual.**
- `codehood grade EXAM QUESTION` em Textual, com os atalhos do chalk.
- Só vale se a interface web de correção não cobrir o caso.

**Fase 6. Ajustes e desclassificações.**
- Decidir se `Feedback` ganha ajustes (atraso, override) ou se isso fica no
  `grades.py` local.

**Descartar:** plágio, transformações de texto, XLSX, `plugins/`,
`contrib/debug`, `contrib/tmp`, `tui/`, `data/disqualifiers.py`, o `dbg()`
global.


## Decisões em aberto

- **D1. O codehood terá modo local (exame aplicado fora: Moodle, Forms,
  papel)?** Se sim, a CLI precisa importar submissões CSV para o servidor,
  ou manter um fluxo só local. Se não, `collect`/`extract` e o
  `submissions.csv` morrem.
- **D2. GitHub Classroom continua?** O codehood hospeda repositórios
  próprios. Se as turmas migram para ele, `contrib/github/classroom` sai.
- **D3. Escala única de nota.** Sugestão: [-1, 1] do mdq por questão e
  porcentagem só na apresentação, alinhando `ExamResult`.
- **D4. Onde fica o autograder.** Subcomando da CLI ou pacote separado
  (`codehood-grader`) que pode rodar em servidor de CI.
- **D5. Turmas antigas do chalk.** Migrar os dados para o codehood ou só
  arquivar como estão.
