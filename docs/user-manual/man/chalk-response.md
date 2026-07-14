# chalk-response(1)

## NAME

chalk-response - view, import, and export student responses

## SYNOPSIS

chalk response <subcommand> <args> <options>

## DESCRIPTION

Handles response-level workflows for a given quiz.

## SUBCOMMANDS

- view ASSIGNMENT QUESTION STUDENT
- transform [ASSIGNMENT QUESTION]
- validate [ASSIGNMENT QUESTION]

## OPTIONS

### chalk response view ASSIGNMENT QUESTION STUDENT

`--plain` 
:   Display the response in plain text format, stripping any formatting or metadata.

`-o, --output PATH`
:   Write the response to the specified file path instead of standard output.


### chalk response transform [ASSIGNMENT QUESTION]

Perform transformations to response data, such as normalization, text formatting, etc.

User can declare custom transformations at `<project_root>/scripts/`. The scripts 
should be named `<name>.transform.<ext>`.

`-s, --student STUDENT_PATTERN`
:   Filter responses to specific students.

`-f, --force`
:   Apply the transformation and overwrite existing responses without confirmation.

`-t, --transform TRANSFORM`
:   Specify the transformation to apply.

`-l, --list`
:   List available transformations without applying any changes.

`-n, --new [FORMAT]` 
:   Create a new transformation script with the specified format (e.g., py, sh)
    and open it for editing.

### chalk response validate [ASSIGNMENT QUESTION]

Validate responses for a given quiz or question.

User can declare custom validators at `<project_root>/scripts/`. The scripts 
should be named `<name>.validate.<ext>`.

`-s, --student STUDENT_PATTERN`
:   Filter responses to specific students.

`-f, --force`
:   Apply the validation and overwrite existing responses without confirmation.

`-v, --validator VALIDATOR`
:   Specify the validation to apply.

`-l, --list`
:   List available validators without applying any changes.

`-n, --new [FORMAT]`
:   Create a new validation script with the specified format (e.g., py, sh)
    and open it for editing.


## EXAMPLES

```bash
# See some student submission
chalk response view exam-01 q1 s123 

# Transform responses for a quiz
chalk response transform exam-01 q1 -s s123 -t text.lowercase
```

## EXIT STATUS

- 0: Command completed successfully.
- 1: Response command failed.

## SEE ALSO

- chalk(1)
- chalk-grade(1)
