# Commands

Run `chalk COMMAND --help` for the options of each command.

```text
chalk
├── init         create chalk.toml and roster.csv in the current directory
├── info         show the classroom configuration
├── roster
│   ├── show     show the roster
│   ├── add      add one student
│   ├── import   merge students from another spreadsheet
│   └── validate check ids, required fields and submissions
├── quiz
│   ├── list     list quizzes
│   └── create   create a quiz
├── question
│   ├── list     list the questions of a quiz
│   └── show     show one question
├── show         show a quiz, a question, answers or grades
├── collect      gather the answers to a question in one file
├── extract      move answers between submissions.csv and one file per student
├── autograde    grade a question with its answer key or autograder script
├── grade        grade answers by hand
├── clear        remove temporary files
├── codehood
│   └── grades   write quiz grades to codehood's grades.csv
└── contrib      run a contrib module (GitHub Classroom, converters...)
```
