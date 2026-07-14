Chalk classroom manager
=======================

Chalk is a CLI tool for classroom management. It helps teachers manage
quizzes, students, and grades. Chalk is a CLI-based tool that assumes that
information is better stored in local text files instead of a complex opaque
database.


Installation
------------

The easier way to run Chalk is to use uvx or pipx:

```bash
uvx chalk  # or pipx run chalk
```

You can add it to your BASH or ZSH profile for easier access,

```bash
echo 'alias chalk="uvx chalk"' >> ~/.bashrc  # or ~/.zshrc
source ~/.bashrc  # or ~/.zshrc
```

or install it globally using pip:

```bash
pip install chalk
```

If you use Windows, consider replacing your operating system with something 
decent that is not trying to spy on you 🧐. 

Usage
-----

To get started with Chalk, simply run the `chalk init` command in your terminal.
It will create a chalk.toml configuration file and the necessary directory
structure for your classroom.


Directory Structure
-------------------

Chalk organizes its data in a simple directory structure. Each classroom is
stored in a separate directory, which contains text files for students,
quizzes and grades. A basic structure looks like this:

```
classroom/
├── reports/
│   ├── midterm.grades.csv
│   └── final.grades.csv
├── data/
│   ├── ...
│   ├── student_n/
│   └── conf.yaml
├── midterm/
│   ├── student_1/
│   ├── ...
│   ├── student_n/
│   └── conf.yaml
├── final/
│   └── conf.yaml
├── chalk.toml
└── roster.csv
```

Data can be stored in a variety of formats, including JSON, CSV, XLSX, YAML and
more. This flexibility allows teachers to choose the format that best suits
their needs and preferences.


Basic commands
--------------

- `chalk init`: Initializes a new classroom.
- `chalk add -is <student_id>`: Adds a new student to the roster.
- `chalk add -ia <quiz_name>`: Adds a new quiz to the classroom.
- `chalk grade -is <student_id>`: Assigns a grade to a student for a specific quiz.
- `chalk report -a <quiz_name>`: Generates a report for a specific quiz.
- `chalk report -s <student_id>`: Generates a report for a specific student.


File formats
------------

### Roster

The roster can be stored in a table form (e.g., CSV, XLSX) or a list form (e.g.,
JSON, YAML). Columns simply correspond to fields in the student model, and empty
cells are translated to null values.

**Examples**

A almost minimal example of a roster in CSV 

```csv
id,name,email
1234,John Doe,john.doe@example.com
5678,Alice Smith,
```
and YAML

```yaml
- id: "1234"
  name: "John Doe"
  email: "john.doe@example.com"
- id: "5678"
  name: "Alice Smith"
```

The columns `name` and `id` are required. Additional optional columns are:

- `age`: The student's age.
- `email`: The student's email address.
- `github`: The student's GitHub username.
- `email_alt`: The student's alternative email address


### Simple quizzes

A simple quiz store all information (including grades and submission data)
in a single file. The example below shows a simple quiz in YAML.

```yaml
name: "Midterm Exam"
data:
  "1234":
    q1: 
      answer: "42"
      grade: 100
    q2:
      answer: "Rio de Janeiro"
      grade: 0
      feedback: "The capital moved to Brasilia in 1960."
  "5678":
    q1:
      answer: "0"
      grade: 50
    q2:
      answer: "Brasilia"
      grade: 100
```

The table representation is a little more complex since it must handle nested data.
The table can be stored in a single file like so:

```csv
id,q1.answer,q1.grade,q2.answer,q2.grade,q2.feedback
1234,42,100,Rio de Janeiro,0,"The capital moved to Brasilia in 1960."
5678,0,50,Brasilia,100,
```

Or it can be split into multiple files:

```csv
# midterm.csv
id,q1,q2
1234,42,Rio de Janeiro
5678,0,Brasilia
```

```csv
# midterm.grades.csv
id,q1,q2
1234,100,0
5678,50,100
```

```csv
# midterm.feedback.csv
id,q1,q2
1234,,"The capital moved to Brasilia in 1960."
5678,,
```

The csv might add an optional row with an empty id to specify additional
information:

```csv
id,q1.answer,q2.answer,q1.grade,q2.grade,q1.feedback,q2.feedback
,42,Rio de Janeiro,100,100,,
```

