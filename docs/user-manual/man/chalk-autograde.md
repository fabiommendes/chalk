# chalk-grade(1)

## NAME

chalk-autograde - compute, adjust, and report grades

## SYNOPSIS

chalk autograde <subcommand> <args> <options>

## DESCRIPTION

Provides automatic grading commands.

## SUBCOMMANDS

- new ASSIGNMENT QUESTION
- run ASSIGNMENT QUESTION
- try ASSIGNMENT QUESTION
- list [ASSIGNMENT]

## OPTIONS

### chalk autograde new [ASSIGNMENT QUESTION TEMPLATE]

Create a new autograder script for the specified quiz and question.

`-l, --list-templates [FILTER]` 
: List available autograder templates without creating a new script. Optionally, 
  provide a filter to narrow down the list.

`-e, --explain`
: Display a detailed explanation of the autograder script structure and how to 
  customize it.

### chalk autograde run ASSIGNMENT [QUESTION]

Run the autograder for the specified quiz and question.

`-y, --yes` 
: Automatically confirm any prompts during the grading process.

`-d, --dry-run` 
: Simulate the grading process without making any changes to grades or feedback.

`--all` 
: Regrade all students, not just those who haven't been graded yet.

`-s, --student STUDENT`
: Specify a student to grade.

`--sort FIELD`
: Sort the output by the specified field.

`-f, --format FORMAT`
: Specify the output format.

`-o, --output PATH`
: Specify the output file path.

`-l, --list`
: List available autograder plugins without running any grading.


### chalk autograde try ASSIGNMENT [QUESTION]

Run the autograder for the specified quiz and question on a single test
submission. It is intended for testing and debugging the autograder script and
it does not affect the actual grades or feedback.

`-s, --student STUDENT`
: Specify a student to test.


### chalk autograde list [ASSIGNMENT [QUESTION]]

List all autograded questions in the specified quiz and display statistics
about the grading process.

## EXAMPLES

```bash
# Create new autograder scripts for
chalk autograde new exam-01 q1

# Run the autograder for all questions in exam-01
chalk autograde run exam-01
```

## SEE ALSO

- chalk(1)
- chalk-report(1)
- chalk-grade(1)
- chalk-script(1)