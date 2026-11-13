# Commands

Run `chalk COMMAND --help` for the options of each command, or see the
[command reference](cli.md).

```text
chalk
├── init         create chalk.toml and roster.csv in the current directory
├── show         show the classroom, a quiz, a question, the roster or answers
├── grade        grade answers by hand
├── autograde    grade a question with its answer key or autograder script
├── extract      move answers between submissions.csv and one file per student
├── clear        remove temporary files
├── info         show the versions of chalk and its dependencies
├── roster
│   ├── add      add one student
│   ├── import   merge students from another spreadsheet
│   └── validate check ids, required fields and submissions
├── quiz
│   └── create   create a quiz
├── codehood
│   ├── grades   write quiz grades to codehood's grades.csv
│   └── autograde grade the code and objective answers of a codehood exam
└── contrib      run a contrib module (GitHub Classroom, converters...)
```

Every reading goes through `chalk show`; the other commands change files.

## Showing things

`chalk show [LOC]` takes a quiz (`p1`) or a question (`p1/q1`). Without
`LOC` it shows the classroom.

| `LOC`   | Without options                      | `-g`                     | Other options                                       |
|---------|--------------------------------------|--------------------------|-----------------------------------------------------|
| empty   | classroom summary and its quizzes    | grades of every quiz     | `--roster`: the roster                              |
| `p1`    | questions of the quiz with statistics | grades of the quiz      |                                                     |
| `p1/q1` | the question and its metadata        | grades of the question   | `--answers`: every answer; `--student ID`: one      |

- `-f FORMAT` and `-o FILE` export any table as `table`, `csv`, `json` or
  `yaml`. Without `-f`, the extension of `-o` decides. `--answers` also takes
  `md`, its default.
- `-s COLUMN` sorts tables; `-s -COLUMN` sorts in descending order.
- `--student ID` with `-g` keeps only the row of that student. The id may be
  approximate (name, username).
- `chalk show -f json` writes the classroom and its quizzes as data.

```sh
chalk show p1 -g -o p1.csv          # grades of p1 as CSV
chalk show -g --final -f json       # final_grade() of conf.py per student
chalk show --roster -s -name        # roster in reverse name order
chalk show p1/q3 --answers -o q3.md # every answer to q3 in one file
```

## Grading codehood answers

`chalk codehood autograde` grades the answers of a
[codehood](https://github.com/fabiommendes/codehood) exam and writes the
grades back through the REST API: the code answers with the autograder
profiles, and the objective ones with the answer key of the mdq question. Run
it at the root of the course.

```text
chalk codehood autograde EXAM[/QUESTION] [-n/--dry-run]
                         [--server URL] [--key-file FILE]
chalk codehood autograde --check GRADER
chalk codehood autograde --try GRADER FILE
```

The course has a `codehood.toml`, and a grader for each question:

```toml
# codehood.toml
[course]
discipline = "paradigmas"
instructor = "ada"
edition = "2026-1"

[server]
url = "https://codehood.example.org"
```

```text
course/
├── questions/logico/fatorial.md     # frontmatter: id: prolog-fatorial
└── graders/logico/fatorial/
    ├── grader.yaml                  # the `autograder:` block of a question
    ├── template/tests.pl            # tests and trusted files
    └── solution/answer.pl           # reference solution (file or directory)
```

- The grader of `questions/<path>.md` is `graders/<path>/`, and the question
  slug on the server is the `id` of its frontmatter. A grader without a
  question is an error; a question without a grader is left alone.
- `grader.yaml` is the `autograder:` block described in
  [Autograding scripts](autograding-scripts.md). Without `profile`, it comes
  from the `highlight` of the question: `prolog` is `prolog-plunit`, `elm` is
  `elm-test` and `python` is `python-pytest`. The `[profiles]` of `chalk.toml`
  apply too.
- The key of a `BOT` API key comes from `CODEHOOD_BOT_KEY` or `--key-file`.
  It is never passed to the graded code.
- Before grading a class, the reference solution must get the full score;
  otherwise the question is skipped and reported.
- Only the newest submission of each closed attempt is graded, when its status
  is `PENDING_GRADE` or `GRADED_AUTOMATICALLY` and no human has written
  feedback on it. Running again updates the grade chalk wrote before (`ref`
  `chalk`).
- If the answer has markdown code fences, only the contents of the fenced
  blocks are graded; otherwise the whole text is.
- The score is sent as a fraction. The feedback has one line per test (✓ or
  ✗). Suspicious code and what the guard refused go to `notes`, which only
  the teacher sees. A timeout or a build error writes 0, unless the grader
  sets `on_build_error: manual`: then nothing is written and the answer stays
  pending, listed as "manual" in the report.
- An error of the infrastructure (sandbox, profile, prepare) writes nothing
  and appears in the report; the exit code is 1.
- A question of the exam without a grader is objective when
  `questions/` has a Markdown file with its `id` and mdq can grade it
  (multiple choice, multiple selection, true or false, numeric, ordering,
  matching...). Essays are left alone. The answer saved on the server is
  already an mdq response and is graded with the key of the file; the score
  is the one of mdq, so it can be negative, and the feedback is the one of the
  choices the student got wrong. An invalid answer (a choice the question does
  not have) is written nowhere and counts as an error.
- The file must be the version on the server: its md5 is compared with the
  `version` of the question, and a question that differs is not graded and
  appears in the report. Push the question first.
- `-n/--dry-run` writes nothing and prints the distribution of the scores.
- `--check` grades the reference solution of a grader folder, and `--try`
  grades a local file. Neither needs a server or a key.

### Reusing a course question in a quiz

A quiz of the same repository can reuse the question with `source:` in its
`conf.yaml`:

```yaml
questions:
  - id: fatorial
    source: ../questions/logico/fatorial.md
```

`chalk autograde p1/fatorial` then grades with `graders/logico/fatorial/`,
the same grader (and the same code fences rule) as `chalk codehood autograde`,
and `--check` uses its `solution/`. An `autograde.*` script in the question
folder of the quiz has priority over the course grader. The `[profiles]` come
from the `chalk.toml` at the root of the course.
