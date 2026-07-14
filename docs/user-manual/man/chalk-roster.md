# chalk-roster(1)

## NAME

chalk-roster - manage students roster

## SYNOPSIS

chalk roster <subcommand> <args> <options>

## DESCRIPTION

Handles student listing, insertion, import, and data validation.

## SUBCOMMANDS

- show
- add
- import
- validate

## OPTIONS

### chalk roster show

Show the current student roster. It can be sorted and formatted for output.

`-s, --sort FIELD`
:   Sort students by the specified field (e.g., name, id). Prefix with `-` for descending order.

`-f, --format FORMAT`
:  Output format (e.g., table, csv, json, yaml).


### chalk roster add [STUDENT_ID]

Adds the specified student or enters the interactive mode in which the user is
prompted to enter student details.

`-n, --name TEXT`
:   Specify the student's name.

`-e, --email TEXT`
:   Specify the student's email.

`-g, --github TEXT`
:   Specify the student's GitHub username.

`--email-alt TEXT`
:   Specify an alternative email for the student.


### chalk roster import PATH

Import roster data from file in PATH. It uses the extension to guess the file
format.

`-r, --replace, -k, --keep` 
:   Replace or keep the old students if conflicts are found. By default it 
tries to merge the imported students with the existing roster.


### chalk roster validate

Validate the roster data for consistency and completeness.

`--id REGEX`
:   Checks if all student IDs match the provided regular expression.

`--fields FIELD1,FIELD2,...`
:   Check for missing required fields.

`--quiz ASSIGNMENT_ID`
:   Validate that all students have submissions for the specified quiz.

`--yes/--no`
:   Automatically answer yes or no to all prompts during validation.


## EXAMPLES

```bash
# Show roster sorted by name
chalk roster show --sort name

# Add a student with ID s123
chalk roster add s123 --name "Alice" --email alice@example.com

# Add students in interactive mode
chalk roster add

# Import roster from CSV, merging with existing data
chalk roster import roster.csv --merge

# Validate that all student IDs follow the pattern s[0-9]{3} and have name and email fields
chalk roster validate --id "s[0-9]{3}" --fields name,email


## SEE ALSO

- chalk(1)
