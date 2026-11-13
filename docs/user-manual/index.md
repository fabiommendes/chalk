# User Manual

Chalk keeps a classroom in a directory of text files. The README of the
project shows the layout, the question
and roster formats, and a quick start. This manual adds the details.

- [Commands](commands.md): the command tree.
- [Autograding scripts](autograding-scripts.md): how chalk runs a grading
  script for each answer.

## Sharing a repository with codehood

A chalk classroom and a codehood course can live in the same directory.
codehood only reads its own files (`codehood.toml`, `README.md`,
`calendar.md`, `grades.csv`, `grades.py`, `questions/`, `exams/` and
`resources/`), and chalk only treats as a quiz a directory with a
`conf.yaml`. Both read `roster.csv`, in the format described in the README.

If the directory has a `codehood.toml`, `chalk init` adds `chalk.toml` to the
course's `.codehoodignore`, and `chalk quiz create ID` adds `ID/`. Lines
already listed are not repeated, and the other lines are kept. Without a
`codehood.toml`, chalk does not touch `.codehoodignore`.

`chalk codehood grades` writes one column per quiz to `grades.csv`, with the
quiz grade in percent, keyed by the roster's id column (`school_id` by
default). Columns that are not quizzes and rows of students outside the
roster are kept, so the file can also hold scores typed by hand. The course's
`grades.py` reads the quiz columns from `student.scores`.
