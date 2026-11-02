# Autograding scripts

Chalk can grade student submissions based on a custom grading script. Chalk
prepares each submission, set a a working directory, collect grades, and clean
up after grading. It however **DO NOT** provide any sandbox or security
mechanism, so it is the responsibility of the instructor to ensure that the
grading script is safe to run. We recommend using bwrap, docker or similar tools
to isolate the grading script if you need to execute untrusted code.

The mechanism is kept intentionally simple and flexible, so that instructors can
implement their own grading logic for different types of quizzes.

Chalk assumes that each submission is graded separately, so we can create
grading scripts for specific questions, but not for a whole quizzes. Chalk
communicates with the grading script through environment variables and an some
specially constructed files, so you can create it in any language you want.

Consider a course with a quiz named `final-exam` and a question named
`q1`. Chalk will look for a grading script in the following path:

```
course/
└── final-exam/
    └── q1/
        ├── autograde.sh
        └── template/
```

Any executable file named `autograde.*` is fine. You can also specify files on
different locations using the option `autograder.script` of the question in
the quiz's `conf.yaml`:

```yaml
# final-exam/conf.yaml
questions:
  - id: q1
    autograder:
      script: the-grading-script.py
```

Now that chalk knows where to find the grading script, we need to understand how
it communicates with it and how it prepares each submission for grading.

When the grading process starts, it creates a temporary working directory at
`<root> / <quiz> / <question> / tmp-<timestamp>`:

```
course/
└── final-exam/
    └── q1/
        ├── autograde.sh
        ├── template/
        └── tmp-2026-04-27/
            ├── student-1/
            ├── ...
            └── student-n/
```

Before grading each submission, chalk copies the contents of the `template/` to
the student's working directory. It also copies the answer of each student to a
file named `answer.txt` in the student's working directory. The name of the file
can be changed setting the option
`autograder.answer` of the question in the quiz's `conf.yaml`:

```yaml
# final-exam/conf.yaml
questions:
  - id: q1
    autograder:
      script: autograde.sh
      answer: src/submission.py
```

Chalk than sets a few environment variables and executes the grading script. The
variables are described in the following table:

| Variable             | Default      | Description                                              |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_STUDENT        |              | ID of the student who submitted the answer.              |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_QUESTION       |              | ID of the question being graded.                         |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ASSIGNMENT     |              | ID of the quiz being graded.                             |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ROOT           |              | Absolute path to the working directory of the submission |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_RESULT         |              | Absolute path of the file where the grading script       |
|                      |              | writes the result (see "Results" below).                 |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ANSWER         | `answer.txt` | Name of the file where the student's answer is saved     |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ANSWER_CONTENT |              | The student's answer itself, as text                     |
| -------------------- | ------------ | -------------------------------------------------------- |


Chalk also saves the same information in a file named `chalk.json`. The script
may choose the most convenient method to access this data. This is an example 
of a `chalk.json` file:

```json
{
  "course": "final-exam",
  "question": "q1",
  "student": "student-1",
  "root": "/path/to/course/final-exam/q1/grading-<timestamp>/student-1",
  "answer": "src/submission.py",
  "answer_content": "print('Hello, world!')\n"
}
```

> [!WARNING]
> A subtle difference between both approaches is that environment variables only
> support strings. The field "answer_content" may hold arbitrary JSON data depending
> on the type of submission. For example, a multiple selection question would 
> hold a list of selected string choices, a numerical question may hold a number 
> and so on. In most cases, we will use autograder to grade programming quizzes, 
> or some kind of text-based submission, so the difference is irrelevant.

## Results

The script writes the result to the file in `CHALK_RESULT`. The file is
created outside the working directory, so code started from the working
directory has no reason to touch it. Chalk detects the format from the
content:

- **Plain text.** The first line is the score and the other lines are the
  feedback shown to the student. The score may be a number (`0.8`), a
  percentage (`80%`) or a fraction (`3/4`).

  ```sh
  echo "3/4" > "$CHALK_RESULT"
  echo "The edge case x=0 is not handled." >> "$CHALK_RESULT"
  ```

- **JSON.** `{"score": 0.75, "feedback": "..."}`, `{"pass": 3, "fail": 1}`,
  or a report from `pytest-json-report`.
- **JUnit XML.** Any file that starts with `<`. The score is passed tests
  over passed plus failed plus errored ones; skipped tests do not count.
  The feedback lists the tests that did not pass. Most test runners write
  JUnit: `pytest --junit-xml="$CHALK_RESULT"`,
  `elm-test --report junit > "$CHALK_RESULT"`, jest with `jest-junit`,
  `cargo nextest`, `gotestsum`.

Chalk never reads the score from the script output. Standard output and
standard error go to the grading log (`chalk.stdout` in the working
directory), and a copy of the result is saved as `chalk.result`. A script
that writes no result file gets an error score.
