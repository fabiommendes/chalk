Chalk classroom manager
=======================

Chalk is a command line tool to grade quizzes and keep track of students and
grades. Everything lives in plain text files in a directory: a roster, one
directory per quiz, the submissions and the grades. Chalk grades what was
answered outside of it (a paper exam, a Moodle or Google Forms export, GitHub
Classroom repositories), either automatically or by hand.

Chalk can share a repository with a codehood course:
both read the same `roster.csv`, and `chalk codehood grades` writes the quiz
grades to the `grades.csv` that codehood publishes.


Installation
------------

```bash
uvx chalk  # or pipx run chalk
```

Chalk needs Python 3.13 or newer.


Getting started
---------------

```bash
chalk init                          # creates chalk.toml and roster.csv
chalk quiz create p1 --questions 3  # creates p1/conf.yaml
# write the questions in p1/questions/ and the answers in p1/submissions.csv
chalk autograde p1 q1               # grades q1 with its answer key
chalk grade p1/q3                   # grades q3 by hand
chalk show p1 --grades              # shows the grades table
```


Directory structure
-------------------

```
classroom/
├── chalk.toml           # classroom configuration
├── roster.csv           # students
├── conf.py              # optional: final_grade() and other hooks
└── p1/                  # a quiz: any directory with a conf.yaml
    ├── conf.yaml        # name, dates, weight and chalk settings of questions
    ├── questions/       # question documents in the mdq format
    │   ├── q1.md
    │   └── q2.yaml
    ├── q3/              # files of question q3: autograder script, template/
    ├── submissions.csv  # one row per student, one column per question
    └── grades.csv       # written by chalk
```


Questions
---------

Objective questions are [mdq](https://pypi.org/project/mdq/) documents in
`<quiz>/questions/`, named after the question id. The document may be
Markdown (`.md`, `.mdq.md`) or the parsed form of mdq in YAML or JSON. It
holds the stem, the choices and the answer key, and chalk grades responses
with mdq.

```markdown
---
id: q1
title: Capital
---

What is the capital of Brazil?

- [*] [df] Brasília
- [ ] [sp] São Paulo
```

`conf.yaml` lists the questions in order and keeps what is specific to chalk:

```yaml
name: Exam 1
weight: 1
questions:
  - id: q1             # mdq document in questions/q1.md
  - id: q2
    value: 2           # weight of the question in the quiz
  - id: q3             # no document: an open question, graded by hand
  - id: q4
    type: text         # free text, graded by an autograder script or a regex
    format: python
  - id: q5
    type: repo         # the answer is a directory, graded by a script
```

Answers in `submissions.csv` follow the mdq responses: the id of a choice (or
its text) for multiple choice, a list of ids such as `a, c` or `[a, c]` for
multiple selection, a number for numeric questions and text for the others.

```csv
id,q1,q2,q3
1234,df,"a, c",An open answer
```


Roster
------

`roster.csv` uses the columns that codehood also uses. Every column is
optional, and other columns are kept.

```csv
school_id,username,name,email,github,status
1234,jdoe,John Doe,john.doe@example.com,jdoe,active
```

The student id is `school_id`. Set `student_id = "username"` (or another
column) in the `[chalk]` section of `chalk.toml` to use another column.
Rosters with an `id` column instead of `school_id` also work.


Documentation
-------------

```bash
uv sync --group dev
uv run mkdocs serve
```
