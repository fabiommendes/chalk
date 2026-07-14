# chalk-script(1)

## NAME

chalk-script - run external scripts in Chalk context

## SYNOPSIS

chalk script <script-name> <options>

## DESCRIPTION

Executes an external script while passing quiz, student, and question context.

## OPTIONS

- -a, --quiz ASSIGNMENT_ID
- -s, --student STUDENT_ID
- -q, --question QUESTION_ID
- --arg KEY=VALUE
- --timeout SECONDS
- --fail-fast
- --dry-run

## EXAMPLES

```bash
chalk script grade_exam --quiz exam-01
```

## EXIT STATUS

- 0: Script finished successfully.
- 1: Script execution failed.

## SEE ALSO

- chalk(1)
