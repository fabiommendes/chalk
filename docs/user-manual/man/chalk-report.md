# chalk-report(1)

## NAME

chalk-report - generate user-facing grade reports

## SYNOPSIS

chalk report <subcommand> <args> <options>

## DESCRIPTION

Creates reports by class, assignment, student, or student detail.

## SUBCOMMANDS

- class
- assignment ASSIGNMENT_ID
- student STUDENT_ID
- student-detail STUDENT_ID

## OPTIONS

### chalk report class

- --sort-students FIELD
- --sort-assignments FIELD
- --include-missing
- -f, --format FORMAT
- -o, --output PATH

### chalk report assignment ASSIGNMENT_ID

- --include-questions
- --include-feedback
- --sort FIELD
- -f, --format FORMAT
- -o, --output PATH

### chalk report student STUDENT_ID

- -a, --assignment ASSIGNMENT_ID
- --include-answers
- --include-feedback
- -f, --format FORMAT
- -o, --output PATH

### chalk report student-detail STUDENT_ID

- -a, --assignment ASSIGNMENT_ID
- --with-metadata
- -f, --format FORMAT
- -o, --output PATH

## EXAMPLES

```bash
chalk report class --format csv --output reports/class.csv
chalk report assignment exam-01 --include-questions
chalk report student s123 --include-feedback
```

## EXIT STATUS

- 0: Command completed successfully.
- 1: Report command failed.

## SEE ALSO

- chalk(1)
- chalk-grade(1)
