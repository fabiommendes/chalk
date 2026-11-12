# Command reference

**Usage**:

```console
$ chalk [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `init`: Initialize a new Chalk project.
* `grade`: Manually grade responses for a question.
* `autograde`: Run the autograder for the specified quiz...
* `info`: Show the version of chalk and of its main...
* `contrib`: Load a contrib module.
* `clear`: Clear the files chalk generates: the cache...
* `show`: Show the classroom, a quiz, a question,...
* `extract`: Move answers from responses.csv to...
* `roster`: Manage the student roster.
* `quiz`: Manage quizzes.
* `codehood`: Exchange data with a codehood course in...

## `chalk init`

Initialize a new Chalk project.

**Usage**:

```console
$ chalk init [OPTIONS]
```

**Options**:

* `-c, --classroom TEXT`: Classroom name
* `--teacher TEXT`: Teacher&#x27;s name
* `--help`: Show this message and exit.

## `chalk grade`

Manually grade responses for a question.

**Usage**:

```console
$ chalk grade [OPTIONS] [LOC]
```

**Arguments**:

* `[LOC]`: Location of the questions to separate responses for (e.g. &#x27;quiz1/q1&#x27;)

If only the quiz is provided, separate all textual questions.

**Options**:

* `-a, --all`: Grade all responses, even if they already have grades
* `-w, --width INTEGER RANGE`: Width of the answer display panel  [default: 80; 20&lt;=x&lt;=200]
* `--help`: Show this message and exit.

## `chalk autograde`

Run the autograder for the specified quiz and question.

**Usage**:

```console
$ chalk autograde [OPTIONS] LOC
```

**Arguments**:

* `LOC`: Quiz/question (e.g. &#x27;p1/q1&#x27;). With only the quiz, asks for the question.  [required]

**Options**:

* `--timeout SECONDS`: Timeout for the autograder script (in seconds). Defaults to autograder.timeout in conf.yaml, or 30.
* `-y, --yes`: Automatically confirm any prompts during the grading process
* `-n, --dry-run`: Simulate the grading process without making any changes to grades or feedback
* `--keep-files`: Keep temporary files generated during grading (for debugging)
* `--keep-failed`: Keep temporary files when autograder script exits with an error (for debugging)
* `--limit N`: Grade only the first N students of the roster
* `--all`: Regrade all students, not just those who haven&#x27;t been graded yet
* `--student STUDENT`: Specify a student to grade
* `-s, --sort FIELD`: Sort the output by the specified field
* `-f, --format FORMAT`: Specify the output format (e.g. &#x27;table&#x27;, &#x27;json&#x27;, etc.)
* `-o, --output PATH`: Specify a file to save the output to
* `-v, --verbose`: Show detailed output during the grading process
* `--run`: Run the autograder for each student and show its output. Saves nothing.
* `--check`: Grade the reference solution of the question and fail unless it gets the full score. Nothing is saved.
* `--help`: Show this message and exit.

## `chalk info`

Show the version of chalk and of its main dependencies.

The classroom and its quizzes are in `chalk show`.

**Usage**:

```console
$ chalk info [OPTIONS]
```

**Options**:

* `-d, --debug`: Add the paths of the classroom and the environment.
* `-f, --format TEXT`: The output format (console, json, yaml).  [default: console]
* `--help`: Show this message and exit.

## `chalk contrib`

Load a contrib module.

**Usage**:

```console
$ chalk contrib [OPTIONS] [MODULE]
```

**Arguments**:

* `[MODULE]`: Module name

## `chalk clear`

Clear the files chalk generates: the cache of the autograder profiles.

The roster, quizzes, submissions and grades are never removed. Files kept
by `autograde --keep-files` live in the system temp directory and stay.

**Usage**:

```console
$ chalk clear [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `chalk show`

Show the classroom, a quiz, a question, the roster or the answers.

Without LOC, shows the classroom and its quizzes; with a quiz, its
questions; with quiz/question, the question. -g shows grades instead.

**Usage**:

```console
$ chalk show [OPTIONS] [LOC]
```

**Arguments**:

* `[LOC]`: Quiz or quiz/question (e.g. &#x27;p1&#x27;, &#x27;p1/q1&#x27;). Empty shows the classroom.

**Options**:

* `-g, --grades`: Show grades instead of the description.
* `--roster`: Show the roster. Takes no LOC.
* `--answers`: Show the answers to a question (LOC is quiz/question).
* `--student ID`: Only this student: its answer to a question, or its row of grades with -g.
* `--final`: With -g and -f/-o, write only the mapping from student ids to final grades.
* `-s, --sort COLUMN`: Sort tables by this column. A &#x27;-&#x27; prefix sorts in descending order.
* `-f, --format FORMAT`: table, csv, json or yaml. --answers also takes md.
* `-o, --output FILE`: Write to this file. The format comes from the extension if -f is missing.
* `--color CHOICE`: Rich text formatting of answers: auto, yes or no.  [default: auto]
* `--total / --no-total`: Include a total column in grade tables.  [default: total]
* `--help`: Show this message and exit.

## `chalk extract`

Move answers from responses.csv to separate files for easier editing or
vice-versa.

**Usage**:

```console
$ chalk extract [OPTIONS] [LOC]
```

**Arguments**:

* `[LOC]`: Location of the questions to separate responses for (e.g. &#x27;quiz1/q1&#x27;)

If only the quiz is provided, separate all textual questions.

**Options**:

* `--ext EXT`: The extension to use for the exported files.
* `--force`: Force overwrite of existing files.
* `-i, --inline`: Inline answers back into the responses.csv file.
* `--help`: Show this message and exit.

## `chalk roster`

Manage the student roster.

**Usage**:

```console
$ chalk roster [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `add`: Add one student to the roster.
* `import`: Import roster data from an external file.
* `validate`: Validate roster data for consistency and...

### `chalk roster add`

Add one student to the roster.

**Usage**:

```console
$ chalk roster add [OPTIONS] [STUDENT_ID]
```

**Arguments**:

* `[STUDENT_ID]`: Student identifier

**Options**:

* `--name TEXT`: Student name
* `--email TEXT`: Student email
* `--github TEXT`: Student GitHub username
* `--email-alt TEXT`: Alternative student email
* `--help`: Show this message and exit.

### `chalk roster import`

Import roster data from an external file.

**Usage**:

```console
$ chalk roster import [OPTIONS] PATH
```

**Arguments**:

* `PATH`: Path to a roster-like file  [required]

**Options**:

* `-r, --replace`: Replace the current roster
* `--keep`: Keep existing students on conflicts
* `--help`: Show this message and exit.

### `chalk roster validate`

Validate roster data for consistency and completeness.

**Usage**:

```console
$ chalk roster validate [OPTIONS]
```

**Options**:

* `--id REGEX`: Regular expression for valid student ids
* `--fields TEXT`: Comma-separated required fields
* `--quiz QUIZ`: Validate that all students have submissions for the specified quiz
* `-y, --yes / --no`: Answer yes (or no) to every prompt of the validation.
* `--help`: Show this message and exit.

## `chalk quiz`

Manage quizzes.

**Usage**:

```console
$ chalk quiz [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `create`: Create a new quiz.

### `chalk quiz create`

Create a new quiz.

**Usage**:

```console
$ chalk quiz create [OPTIONS] QUIZ_ID
```

**Arguments**:

* `QUIZ_ID`: Quiz identifier (e.g. &#x27;hw1&#x27;, &#x27;exam1&#x27;, etc.)  [required]

**Options**:

* `--name TEXT`: Quiz name
* `-q, --questions TEXT`: Number of questions or comma-separated list of question IDs
* `--start [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]`: Start date and time for the quiz (e.g. &#x27;2024-01-01 09:00&#x27;)
* `--end [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]`: End date and time for the quiz (e.g. &#x27;2024-01-01 17:00&#x27;)
* `--help`: Show this message and exit.

## `chalk codehood`

Exchange data with a codehood course in the same repository.

**Usage**:

```console
$ chalk codehood [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `grades`: Write the grade of each quiz, in percent,...
* `autograde`: Grade the code answers of a codehood exam...

### `chalk codehood grades`

Write the grade of each quiz, in percent, to codehood&#x27;s grades.csv.

Quiz columns are replaced; other columns and rows are kept.

**Usage**:

```console
$ chalk codehood grades [OPTIONS]
```

**Options**:

* `-o, --output PATH`: File to update (default: grades.csv at the project root)
* `--help`: Show this message and exit.

### `chalk codehood autograde`

Grade the code answers of a codehood exam and write the grades back.

Reads codehood.toml, questions/ and graders/ of the current directory. The
key of the grading bot comes from CODEHOOD_BOT_KEY or --key-file and is
never passed to the graded code. Answers with human feedback are skipped.

**Usage**:

```console
$ chalk codehood autograde [OPTIONS] [EXAM[/QUESTION]]
```

**Arguments**:

* `[EXAM[/QUESTION]]`: Slug of the exam, and optionally of one of its questions.

**Options**:

* `-n, --dry-run`: Grade, but write nothing; show the distribution.
* `--server URL`: Server URL. Default:  url.
* `--key-file FILE`: File with the key of the grading bot (BOT).
* `--check GRADER`: Grade the reference solution of a grader folder. No server.
* `--try GRADER FILE`: Grade a local file with a grader folder. No server.
* `--help`: Show this message and exit.
