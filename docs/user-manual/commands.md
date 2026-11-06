# Commands

Run `chalk COMMAND --help` for the options of each command.

```text
chalk
├── init         create chalk.toml and roster.csv in the current directory
├── info         show the classroom configuration
├── roster
│   ├── show     show the roster
│   ├── add      add one student
│   ├── import   merge students from another spreadsheet
│   └── validate check ids, required fields and submissions
├── quiz
│   ├── list     list quizzes
│   └── create   create a quiz
├── question
│   ├── list     list the questions of a quiz
│   └── show     show one question
├── show         show a quiz, a question, answers or grades
├── collect      gather the answers to a question in one file
├── extract      move answers between submissions.csv and one file per student
├── autograde    grade a question with its answer key or autograder script
├── grade        grade answers by hand
├── clear        remove temporary files
├── codehood
│   ├── grades   write quiz grades to codehood's grades.csv
│   └── autograde grade the code answers of a codehood exam
└── contrib      run a contrib module (GitHub Classroom, converters...)
```

## Grading codehood answers

`chalk codehood autograde` grades the code answers of a
[codehood](https://github.com/fabiommendes/codehood) exam with the autograder
profiles and writes the grades back through the REST API. Run it at the root
of the course.

```text
chalk codehood autograde --exam SLUG [--question SLUG] [--dry-run]
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
- `--dry-run` writes nothing and prints the distribution of the scores.
- `--check` grades the reference solution of a grader folder, and `--try`
  grades a local file. Neither needs a server or a key.
