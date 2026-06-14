# chalk(1)

## NAME

chalk - classroom management command-line tool

## SYNOPSIS

chalk <global-options> <command> <args> <options>

## DESCRIPTION

chalk manages local classroom data such as roster, assignments, responses, grades, and reports.

## OPTIONS

- --root PATH
- -y, --yes
- -n, --no
- -q, --quiet
- -v, --verbose

## COMMANDS

- init
- info
- roster
- assignment
- question
- response
- grade
- report
- script

## EXAMPLES

```bash
chalk init --classroom calc1 --teacher "Dr. Ada"
chalk roster import --file roster.csv
chalk assignment create exam-01 --questions 10
```

## EXIT STATUS

- 0: Command completed successfully.
- 1: Command failed due to user or runtime error.

## SEE ALSO

- chalk-init(1)
- chalk-roster(1)
- chalk-assignment(1)
- chalk-grade(1)
- chalk-report(1)
