---
type: glossary
status: active
---

# Glossary

The vocabulary of chalk and of its grading engine, chalk-grader: the words
teachers, agents and the code use for classrooms, quizzes and grading.

---

## Adjustment

A change the teacher makes to a grade after grading, with a reason: points given, cancelled, regraded, late or early.

- tags: grading
- related: Grade
- code: chalk.core.adjustment.Adjustment

## Answer

The content of a response: a choice id, a list of ids, a number, a text or a directory, depending on the question.

- tags: grading
- avoid: reply
- related: Response
- code: chalk.core.answer.AnyAnswer

## Answer key

The correct answers of an mdq question, written in its document. chalk grades objective questions against it.

- tags: grading
- avoid: gabarito
- related: Question
- pt: gabarito

## Autograder

The automatic grading of a question, configured in `conf.yaml` under `autograder`: a profile or a script, and its limits.

- tags: engine
- avoid: corrector
- related: Profile, Grader
- code: chalk_grader.models.Autograder

## Classroom

The directory of one class taught by a teacher: `chalk.toml`, the roster and one directory per quiz. It may also be a codehood course.

- tags: classroom
- avoid: project, turma
- related: Quiz, Roster
- code: chalk.core.classroom.Classroom
- pt: turma

## Disqualification

The reason a response gets no score: timeout, invalid input, error, build error or plagiarism. It stands where the score would be.

- tags: grading
- related: Score
- code: chalk.core.disqualification.Disqualification, chalk_grader.disqualification.Disqualified

## Feedback

The text about a response that goes to the student.

- tags: grading
- avoid: comment
- related: Notes, Grade

## Grade

The recorded result of a response or submission: a score or a disqualification, the adjustments, the feedback and the notes. `grades.csv` of the quiz holds them.

- tags: grading
- related: Score, Adjustment, Feedback, Notes
- code: chalk.core.models.ResponseGrade, chalk.core.models.SubmissionGrade

## Grader

Anything that takes the answer of one student and returns a score and feedback: the answer key, a regex, a script or a profile.

- tags: engine
- related: Autograder, Profile
- code: chalk.core.grader.Grader

## Guard

The checks a profile runs inside the test process to stop a student answer from forging the result (for example, the pytest guard).

- tags: engine
- related: Notes, Profile

## Notes

The text about a response that only the teacher sees: signs of tampering, lines of the guard, the internal log of the grader.

- tags: grading
- related: Feedback, Guard
- code: chalk_grader.graded.Graded

## Profile

A grading recipe for one ecosystem, written as data (`elm-test`, `python-pytest`, `rust-cargo`...): the steps, the environment, the files the template controls and how the report is read.

- tags: engine
- avoid: recipe
- related: Template, Sandbox, Reference run
- code: chalk_grader.models.Profile

## Question

One item of a quiz, identified by its id. It is an mdq document, a text or repo question declared in `conf.yaml`, or an open question with no document, graded by hand.

- tags: classroom
- avoid: item, exercise
- related: Quiz, Answer key
- code: chalk.question.base.BaseQuestion

## Quiz

An assessment of the classroom: a directory with a `conf.yaml` that lists its questions, the submissions and the grades.

- tags: classroom
- avoid: assignment
- related: Question, Submission
- code: chalk.core.quiz.Quiz

## Reference run

The run of the build and test steps on the reference solution, once per grader. It fills the cache and fails grading when the solution does not get full score.

- tags: engine
- related: Reference solution, Profile

## Reference solution

The teacher's answer to a code question. The profile grades it before the class to check the grader.

- tags: engine
- avoid: model answer
- related: Reference run, Template

## Response

What a student handed in for one question: the answer and, when known, when it started and ended.

- tags: grading
- related: Answer, Submission
- code: chalk.core.models.Response

## Roster

The list of students of the classroom, in `roster.csv`, with the columns shared with codehood.

- tags: classroom
- avoid: enrollment, class list
- related: Student
- code: chalk.core.roster.Roster

## Sandbox

The isolated environment, built with bwrap, where a profile runs student code: no network, read-only template, resource limits.

- tags: engine
- avoid: jail, container
- related: Profile, Service
- code: chalk_grader.script_runner.Sandbox

## Score

The exact number a grader gives a response, usually in [0, 1] (mdq questions use [-1, 1]); the quiz multiplies it by the value of the question.

- tags: grading
- avoid: points, mark
- related: Grade, Disqualification
- code: chalk_grader.score.Score

## Service

A server the teacher's tests talk to during a run (HTTP, database), started next to the sandbox.

- tags: engine
- related: Sandbox
- code: chalk_grader.services.Services

## Student

A person in the roster, identified by `school_id` unless `chalk.toml` picks another column.

- tags: classroom
- related: Roster
- code: chalk.core.student.Student

## Submission

Everything one student handed in for one quiz: one row of `submissions.csv`, with a response per question.

- tags: grading
- avoid: attempt, entry
- related: Response, Quiz
- code: chalk.core.models.Submission

## Task

What chalk-grader knows about the question it grades: the ids of the question and quiz, its root directory and its template.

- tags: engine
- related: Question, Profile
- code: chalk_grader.task.Task

## Template

The project of the teacher that a student answer is copied into before the tests run: the tests, the build files and the files the student may not change.

- tags: engine
- avoid: skeleton, scaffold
- related: Profile, Reference solution
