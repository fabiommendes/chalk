# chalk-quiz(1)

## NAME

chalk-quiz - manage quiz resources

## SYNOPSIS

chalk quiz <subcommand> <args> <options>

## DESCRIPTION

Creates, lists, inspects, deletes, and converts quiz files.

## SUBCOMMANDS

- list
- create ID
- show ID

## OPTIONS

### chalk quiz list

`-s, --sort FIELD`
:   Sort quizzes by the specified field. Prefix with `-` for descending order.


### chalk quiz create ID

`-n, --name TEXT`
:  Specify a name for the quiz. By default it uses the ID as the name.

`-q, --questions INT`
:  Create the specified number of empty questions in the quiz.

`--start DATETIME`
:  Specify the start date and time for the quiz.

`--end DATETIME`
:  Specify the end date and time for the quiz.

`--split`
:  Split the quiz into separate files.


### chalk quiz show ASSIGNMENT

`-g, --grades`
:  Show a table with all grades for all students.

`-m, --missing`
:  Show a list of students who have not submitted the quiz.


### chalk quiz merge ID1 ID2

`-o, --output ID`
:  Specify the output id for the merged quiz file(s).

## EXAMPLES

```bash
# List quizzes sorted by name in descending order
chalk quiz list --sort -name

# Create a new quiz with 10 questions using YAML format
chalk quiz create exam-01 --questions 10 --format yaml

# Show details of a quiz including questions
chalk quiz show exam-01 --questions
```

## SEE ALSO

- chalk(1)
- chalk-question(1)
- chalk-response(1)
