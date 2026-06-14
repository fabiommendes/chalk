# chalk-grade(1)

## NAME

chalk-grade - compute, adjust, and report grades

## SYNOPSIS

chalk grade <subcommand> <args> <options>

## DESCRIPTION

Display and mark grades for assignments and students. Provides reporting
capabilities for grade summaries and details.

## SUBCOMMANDS

- mark ASSIGNMENT_ID QUESTION_ID
- override ASSIGNMENT_ID QUESTION_ID STUDENT_ID
- view

## OPTIONS

### chalk grade mark ASSIGNMENT_ID [QUESTION_ID]

Mark ungraded submissions for an assignment, optionally limited to a specific
question.

`-s, --student STUDENT` : Grade a specific student.

`--all` : Grade all students, including those with existing grades.


### chalk grade override ASSIGNMENT_ID [QUESTION_ID]

Override existing grades for an specific assignment and question. If QUESTION_ID
is not provided, override the entire assignment grade.

`-s, --student STUDENT` : Override grade for a specific student.

`-a, --all` : Uses the same override grades for all students.

`--only-up, --only-down` : Used together with `--all` to specify whether to only
override grades that are being increased (`--only-up`) or decreased
(`--only-down`).

`--grade GRADE` : The new grade to assign. Can be a numeric value or a letter
grade, depending on the grading scheme.

`--by NUMBER` : Adjust the existing grade by a specified amount. It will add the
given number to the current grade.

`--reason REASON` : Provide a reason for the grade override, which will be
recorded in the grade history.

### chalk grade view

Display grade information for students and assignments.

`-a, --assignment ASSIGNMENT` : Filter grades by a specific assignment.

`-q, --question QUESTION` : Must be used together with `-a` to filter grades by
a specific question. Show detailed information for the grading of that question.

`-s, --student STUDENT` : Filter grades by a specific student.


## EXAMPLES

```bash
# Mark all ungraded submissions for exam-01
chalk grade mark exam-01

# View all final grades
chalk grade view

# View all grades for an exam
chalk grade view -a exam-01

# Mark all ungraded submissions for exam-01 question 1
chalk grade auto exam-01 q1

# Override grade and give points for all students for an specific question
chalk grade override exam-01 q1 --all --grade 0.5 --feedback "Ambiguous question, giving partial credit."
```

## EXIT STATUS

- 0: Command completed successfully.
- 1: Grade command failed.

## SEE ALSO

- chalk(1)
- chalk-report(1)
