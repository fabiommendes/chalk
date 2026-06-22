# chalk-question(1)

## NAME

chalk-question - inspect and transform assignment questions

## SYNOPSIS

chalk question <subcommand> <args> <options>

## DESCRIPTION

Lists questions, inspects one question, extracts choices, and converts question types.

## SUBCOMMANDS

- list ASSIGNMENT
- show ASSIGNMENT QUESTION
- convert ASSIGNMENT QUESTION

## OPTIONS

### chalk question list ASSIGNMENT

`-s, --sort FIELD`
:   Sort questions by the specified field (e.g., id, type).   

`-f, --format FORMAT`
:   Specify the output format (e.g., table, json).   

`-o, --output PATH`
:   Specify the output file path. If not provided, output will be printed to the console.


### chalk question show ASSIGNMENT QUESTION

`-f, --format FORMAT`
:   Specify the output format (e.g., table, json).   

`-o, --output PATH`
:   Specify the output file path. If not provided, output will be printed to the console.


### chalk question choices ASSIGNMENT QUESTION

`-f, --format FORMAT`
:   Specify the output format (e.g., table, json).   

`-o, --output PATH`
:   Specify the output file path. If not provided, output will be printed to the console.


### chalk question convert ASSIGNMENT QUESTION

`-t, --to TYPE`
:   Specify the target question type.   


## EXAMPLES

```bash
# List all questions in the assignment "exam-01"
chalk question list exam-01

# Show details of question "q1" in assignment "exam-01" with statistics
chalk question show exam-01 q1 --with-stats

# Extract choices for question "q2" in assignment "exam-01"
chalk question choices exam-01 q2

# Convert question "q3" in assignment "exam-01" to numeric type
chalk question convert exam-01 q3 --to numeric
```

## EXIT STATUS

- 0: Command completed successfully.
- 1: Question command failed.

## SEE ALSO

- chalk(1)
- chalk-assignment(1)
