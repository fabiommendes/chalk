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
| CHALK_RESULT         | `graded.*`   | Name of the file  where the grading script               |
|                      |              | should write the results.                                |
|                      |              |                                                          |
|                      |              | Chalk can understand results in JSON, YAML or plain      |
|                      |              | text.                                                    |
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

The script can pass the results back to chalk writing back to the file 
specified in the `CHALK_RESULT` variable. Chalk will infer the content type based 
on the file extension, but it accepts JSON, YAML, TOML and plain text. 
For structured formats like JSON, YAML and TOML, it infers the format based on
the structure of the parsed document. For simple numeric grades, the document
may consist of just the corresponding number as a number or string (to preserve decimal 
precision). 

A more sophisticated example is shown below:

```json
{
  "score": 0.75,
  "feedback": "Good job, but you forgot to handle the edge case when x=0.",
  "comments": [
    {
      "line": 10,
      "comment": "This function could be optimized by using a dictionary instead of a list."
    },
    {
      "line": 20,
      "comment": "Consider adding more test cases to cover edge cases."
    }
  ]
}
```

Alternativelly, the grading script may output the results to stdout. Chalk
will try to parse it if no `CHALK_RESULT` file is found. Chalk also ignores
all content before the header line `CHALK RESULT`.


## External tools

Chalk interops with some external tools that might be useful in a grading
context (specially for programming quizzes). ...

# Pytest support 

Chalk understands the output of pytest output. 
