# Chalk CLI Command Tree and Flags (v1)

This document defines the final command tree and the flags for each node.

## Global flags

These flags are available for every command.

- `--root PATH`: Run command using a specific Chalk project root.
- `-y, --yes / -n, --no`: Accept or reject all interactive prompts.
- `-q, --quiet`: Reduce non-essential output.
- `-v, --verbose`: Show extra execution details.

## Full tree

```text
chalk
├── init
├── info
├── roster
│   ├── list
│   ├── add
│   ├── import
│   └── validate
├── quiz
│   ├── list
│   ├── create
│   ├── show
│   ├── delete
│   └── convert
├── question
│   ├── list
│   ├── show
│   ├── choices
│   └── convert
├── response
│   ├── view
│   ├── import
│   └── export
├── grade
│   ├── quiz
│   ├── student
│   ├── auto
│   ├── manual
│   ├── override
│   └── report
├── report
│   ├── class
│   ├── quiz
│   ├── student
│   └── student-detail
└── script
```

## Root commands

### `chalk init`

Initialize a new Chalk classroom project.

Flags:
- `-c, --classroom TEXT`: Classroom name.
- `-t, --teacher TEXT`: Teacher name.
- `--force`: Overwrite existing bootstrap files when safe.

### `chalk info`

Print project summary or resource details.

Flags:
- `-s, --student STUDENT_ID`: Show one student.
- `-a, --quiz ASSIGNMENT_ID`: Show one quiz.
- `-r, --roster`: Include roster table.
- `--sort FIELD`: Sort roster output (`id`, `name`, `email`, `github`).
- `-f, --format FORMAT`: Output format (`console`, `json`, `yaml`).

## `roster` commands

### `chalk roster list`

List students from roster.

Flags:
- `--sort FIELD`: Sort by `id`, `name`, `email`, or `github`.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk roster add STUDENT_ID`

Add one student.

Flags:
- `-n, --name TEXT`: Student display name.
- `-e, --email TEXT`: Primary email.
- `-g, --github TEXT`: GitHub username.
- `--email-alt TEXT`: Alternative email.
- `--force`: Update existing student if ID already exists.

### `chalk roster import`

Import students from external table or data file.

Flags:
- `-f, --file PATH`: Input file path.
- `--merge / --replace`: Merge into existing roster or replace it.
- `--on-conflict MODE`: Conflict mode (`ask`, `overwrite`, `skip`).
- `--id-column NAME`: Column to use as unique student ID.
- `--force`: Skip safety checks.

### `chalk roster validate`

Validate roster consistency.

Flags:
- `--check-duplicates`: Detect duplicated IDs/emails.
- `--check-id-format`: Validate ID naming constraints.
- `--check-required-fields`: Validate required fields.
- `--strict`: Exit non-zero on warnings.
- `-f, --format FORMAT`: Output format (`table`, `json`, `yaml`).

## `quiz` commands

### `chalk quiz list`

List quizzes in project.

Flags:
- `--sort FIELD`: Sort by `id`, `name`, `start`, or `end`.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk quiz create ASSIGNMENT_ID`

Create a new quiz file.

Flags:
- `-n, --name TEXT`: Quiz display name.
- `-q, --questions TEXT`: Number of questions or explicit IDs (repeatable).
- `--start DATETIME`: Quiz start timestamp.
- `--end DATETIME`: Quiz end timestamp.
- `--format FORMAT`: Storage format (`csv`, `json`, `yaml`, `xlsx`).
- `--split`: Split spreadsheet fields across multiple files where applicable.
- `--force`: Overwrite if quiz already exists.

### `chalk quiz show ASSIGNMENT_ID`

Show quiz metadata and optional details.

Flags:
- `--questions`: Include question definitions.
- `--submissions`: Include submission summary.
- `-f, --format FORMAT`: Output format (`table`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk quiz delete ASSIGNMENT_ID`

Delete a quiz.

Flags:
- `--force`: Delete without confirmation.
- `--keep-reports`: Keep report artifacts.

### `chalk quiz convert ASSIGNMENT_ID`

Convert quiz storage format.

Flags:
- `--to FORMAT`: Target format (`csv`, `json`, `yaml`, `xlsx`).
- `-o, --output PATH`: Output path for converted file.
- `--split`: Enable split output when converting to spreadsheet.
- `--force`: Overwrite target files.

## `question` commands

### `chalk question list ASSIGNMENT_ID`

List questions for one quiz.

Flags:
- `--sort FIELD`: Sort by `id`, `type`, or `grade`.
- `-f, --format FORMAT`: Output format (`table`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk question show ASSIGNMENT_ID QUESTION_ID`

Show one question.

Flags:
- `--with-stats`: Include answer distribution and grade summary.
- `-f, --format FORMAT`: Output format (`table`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk question choices ASSIGNMENT_ID QUESTION_ID`

List distinct answer choices observed for a question.

Flags:
- `--sort MODE`: Sort mode (`natural`, `alpha`, `count`).
- `--with-count`: Include frequency of each choice.
- `-f, --format FORMAT`: Output format (`table`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk question convert ASSIGNMENT_ID QUESTION_ID`

Convert question type when conversion is allowed.

Flags:
- `--to TYPE`: Target type (`open`, `single`, `multiple`, `numeric`).
- `--force`: Apply conversion even if data checks warn.

## `response` commands

### `chalk response view ASSIGNMENT_ID QUESTION_ID STUDENT_ID`

Show one student response.

Flags:
- `--plain`: Disable rich formatting.
- `--raw`: Print raw data payload.
- `-f, --format FORMAT`: Output format (`console`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk response import ASSIGNMENT_ID`

Import responses from external source.

Flags:
- `-f, --file PATH`: Input file path.
- `--source TYPE`: Source type (`auto`, `lms`, `csv`, `json`, `yaml`).
- `--on-conflict MODE`: Conflict mode (`ask`, `overwrite`, `skip`).
- `--student-column NAME`: Source column mapping for student ID.
- `--question-map PATH`: Optional mapping file for question IDs.
- `--force`: Skip validation prompts.

### `chalk response export ASSIGNMENT_ID`

Export responses to file.

Flags:
- `-s, --student STUDENT_ID`: Export only one student.
- `-q, --question QUESTION_ID`: Export only one question.
- `-f, --format FORMAT`: Output format (`csv`, `json`, `yaml`, `xlsx`).
- `-o, --output PATH`: Output file path.
- `--include-grades`: Include grades in export.
- `--include-feedback`: Include feedback in export.

## `grade` commands

### `chalk grade quiz ASSIGNMENT_ID`

Compute or show grades for one quiz.

Flags:
- `-s, --student STUDENT_ID`: Limit to one or more students (repeatable).
- `--only-ungraded`: Process only missing grades.
- `--regrade`: Recompute all grades.
- `--sort FIELD`: Sort by `id`, `total`, or question ID.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk grade student STUDENT_ID`

Compute or show student grades across quizzes.

Flags:
- `-a, --quiz ASSIGNMENT_ID`: Limit to one quiz.
- `--regrade`: Recompute all applicable grades.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk grade auto ASSIGNMENT_ID`

Run automatic grading for one quiz.

Flags:
- `--plugin NAME`: Grading script/plugin entrypoint.
- `--only-ungraded`: Grade only responses without grade.
- `--dry-run`: Show grading actions without saving.
- `--force`: Allow overwrite of existing grades.

### `chalk grade manual ASSIGNMENT_ID QUESTION_ID STUDENT_ID`

Set a grade manually.

Flags:
- `--grade FLOAT`: Manual grade value.
- `--feedback TEXT`: Feedback text.
- `--append-feedback`: Append instead of replacing feedback.
- `--force`: Overwrite existing grade/feedback.

### `chalk grade override ASSIGNMENT_ID QUESTION_ID STUDENT_ID`

Override a previously computed grade.

Flags:
- `--grade FLOAT`: New grade value.
- `--feedback TEXT`: Override feedback.
- `--reason TEXT`: Human-readable reason for override.
- `--force`: Apply without confirmation.

### `chalk grade report`

Generate grading-focused report.

Flags:
- `--scope SCOPE`: Scope (`class`, `quiz`, `student`).
- `-a, --quiz ASSIGNMENT_ID`: Scope filter for quiz.
- `-s, --student STUDENT_ID`: Scope filter for student.
- `--sort FIELD`: Sort key.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

## `report` commands

### `chalk report class`

Generate class-wide report.

Flags:
- `--sort-students FIELD`: Sort students by `id`, `name`, or `total`.
- `--sort-quizzes FIELD`: Sort quizzes by `id`, `name`, or date.
- `--include-missing`: Include missing submissions.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`, `xlsx`).
- `-o, --output PATH`: Write output to file.

### `chalk report quiz ASSIGNMENT_ID`

Generate report for one quiz.

Flags:
- `--include-questions`: Include per-question columns.
- `--include-feedback`: Include feedback text.
- `--sort FIELD`: Sort by `id`, `name`, or `total`.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`, `xlsx`).
- `-o, --output PATH`: Write output to file.

### `chalk report student STUDENT_ID`

Generate report for one student.

Flags:
- `-a, --quiz ASSIGNMENT_ID`: Filter one quiz.
- `--include-answers`: Include student answers.
- `--include-feedback`: Include feedback.
- `-f, --format FORMAT`: Output format (`table`, `csv`, `json`, `yaml`).
- `-o, --output PATH`: Write output to file.

### `chalk report student-detail STUDENT_ID`

Generate detailed student report with answers and grading context.

Flags:
- `-a, --quiz ASSIGNMENT_ID`: Optional quiz filter.
- `--with-metadata`: Include timing and source metadata.
- `-f, --format FORMAT`: Output format (`json`, `yaml`, `md`, `txt`).
- `-o, --output PATH`: Write output to file.

## `script` command

### `chalk script SCRIPT_NAME`

Run an external script in Chalk context.

Flags:
- `-a, --quiz ASSIGNMENT_ID`: Provide quiz context.
- `-s, --student STUDENT_ID`: Provide student context.
- `-q, --question QUESTION_ID`: Provide question context.
- `--arg KEY=VALUE`: Extra argument (repeatable).
- `--timeout SECONDS`: Script timeout.
- `--fail-fast`: Stop on first script error.
- `--dry-run`: Print execution plan without running script.

## Aliases (recommended)

- `chalk roster list` -> `chalk roster ls`
- `chalk quiz list` -> `chalk quiz ls`
- `chalk question list` -> `chalk question ls`
- `chalk report quiz` -> `chalk report asg`
- `chalk report student-detail` -> `chalk report student-full`
