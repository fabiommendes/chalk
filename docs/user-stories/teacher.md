---
type: stories
status: active
role: teacher
---

# Teacher user stories

## Objective

### Grade mdq questions from the answer key

    status: implemented

As a teacher, I want multiple choice, multiple selection, true/false, numeric and short-answer questions graded from the answer key in the mdq file, without writing a script.

## Manual

### Grade by hand with shortcuts

    status: partial

As a teacher, I want to go through the answers to a question, one per student, and give a grade and feedback with few keystrokes, with the option to go back and undo.

### Group identical answers

    status: todo

As a teacher, I want to grade at once all identical answers (or answers equal after normalizing whitespace and case), so I do not repeat the same work 40 times.

### Review the suggestion of a grader

    status: todo

As a teacher, I want an automatic grader to suggest a grade and feedback that I only confirm or adjust, for questions where it is right almost always but not always.

## Data

### Grade with my own script

    status: implemented

As a teacher, I want to grade a question with my own script that receives the student's answer as text and returns a grade and feedback, for criteria that fit neither an answer key nor a unit test (relations between parts of the answer, format, a secret given in the statement for the class or the student).

### Grade a regex

    status: implemented

As a teacher, I want the student to hand in a regex that chalk tests against examples that must and must not match, listed in conf.yaml, with a grade proportional to the hits. A regex that takes too long on an example misses that example and does not stall grading.

### Grade code without running it

    status: todo

As a teacher, I want to grade a piece of code by its structure (required or forbidden constructs), without running it, with the criteria listed in conf.yaml.

## Code

### Grade with unit tests

    status: implemented

As a teacher, I want to grade the student's project by running the tests of my template (Python with uv, Elm, JavaScript or another language with a test runner), with grade = passed tests / total, without setting up the sandbox for each exam. The tests may be hidden, and the student cannot change them, add dependencies or forge the grade with a print.

### Build before testing

    status: implemented

As a teacher, I want to grade Rust, C and other compiled languages, where the answer must build before the tests run. A build error shows as such, with the compiler output, and I decide whether it is worth zero or goes to manual grading.

### Compare input and output

    status: implemented

As a teacher, I want to grade a program by comparing its output with the expected one for several inputs, online-judge style, for exercises without a test framework.

### Test against a simulated network

    status: implemented

As a teacher, I want the tests to talk to servers I start (HTTP, database), without internet access.

## Common to all classes

### Rehearse the grader

    status: partial

As a teacher, I want to run the grader against my reference answer and against wrong answers I write, before grading the class, to find a bug in the grader in one run and not in 80 grades.

### Regrade part of the class

    status: implemented

As a teacher, I want to regrade only one student or only one question, after fixing the grader or after a review request, without redoing the rest.

### See the result of each student

    status: partial

As a teacher, I want to see, for each student, the grade, the reason for a zero (timeout, error, build error, empty answer), the feedback that goes to the student and, apart, the internal log of the grader that only I see.
