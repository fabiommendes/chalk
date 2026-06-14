# chalk-assignment(1)

## NAME

chalk-assignment - manage assignment resources

## SYNOPSIS

chalk assignment <subcommand> <args> <options>

## DESCRIPTION

Creates, lists, inspects, deletes, and converts assignment files.

## SUBCOMMANDS

- list
- create ID
- show ID

## OPTIONS

### chalk assignment list

`-s, --sort FIELD`
:   Sort assignments by the specified field. Prefix with `-` for descending order.


### chalk assignment create ID

`-n, --name TEXT`
:  Specify a name for the assignment. By default it uses the ID as the name.

`-q, --questions INT`
:  Create the specified number of empty questions in the assignment.

`--start DATETIME`
:  Specify the start date and time for the assignment.

`--end DATETIME`
:  Specify the end date and time for the assignment.

`--split`
:  Split the assignment into separate files.


### chalk assignment show ASSIGNMENT

`-g, --grades`
:  Show a table with all grades for all students.

`-m, --missing`
:  Show a list of students who have not submitted the assignment.


### chalk assignment merge ID1 ID2

`-o, --output ID`
:  Specify the output id for the merged assignment file(s).

## EXAMPLES

```bash
# List assignments sorted by name in descending order
chalk assignment list --sort -name

# Create a new assignment with 10 questions using YAML format
chalk assignment create exam-01 --questions 10 --format yaml

# Show details of an assignment including questions
chalk assignment show exam-01 --questions
```

## SEE ALSO

- chalk(1)
- chalk-question(1)
- chalk-response(1)
