# Autograding scripts

Chalk can grade student submissions based on a custom grading script. Chalk
prepares each submission, set a a working directory, collect grades, and clean
up after grading. Scripts run in a sandbox by default (see "Sandbox" below).
Python projects tested with pytest need no script at all (see "Python
projects with pytest").

The mechanism is kept intentionally simple and flexible, so that instructors can
implement their own grading logic for different types of quizzes.

Chalk assumes that each submission is graded separately, so we can create
grading scripts for specific questions, but not for a whole quizzes. Chalk
communicates with the grading script through environment variables and an some
specially constructed files, so you can create it in any language you want.

Consider a course with a quiz named `final-exam` and a question named
`q1`. Chalk will look for a grading script in the following path:

```
course/
└── final-exam/
    └── q1/
        ├── autograde.sh
        └── template/
```

Any executable file named `autograde.*` is fine. You can also specify files on
different locations using the option `autograder.script` of the question in
the quiz's `conf.yaml`:

```yaml
# final-exam/conf.yaml
questions:
  - id: q1
    autograder:
      script: the-grading-script.py
```

Now that chalk knows where to find the grading script, we need to understand how
it communicates with it and how it prepares each submission for grading.

When the grading process starts, it creates a temporary working directory at
`<root> / <quiz> / <question> / tmp-<timestamp>`:

```
course/
└── final-exam/
    └── q1/
        ├── autograde.sh
        ├── template/
        └── tmp-2026-04-27/
            ├── student-1/
            ├── ...
            └── student-n/
```

Before grading each submission, chalk copies the contents of the `template/` to
the student's working directory. It also copies the answer of each student to a
file named `answer.txt` in the student's working directory. The name of the file
can be changed setting the option
`autograder.answer` of the question in the quiz's `conf.yaml`:

```yaml
# final-exam/conf.yaml
questions:
  - id: q1
    autograder:
      script: autograde.sh
      answer: src/submission.py
```

Chalk than sets a few environment variables and executes the grading script. The
variables are described in the following table:

| Variable             | Default      | Description                                              |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_STUDENT        |              | ID of the student who submitted the answer.              |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_QUESTION       |              | ID of the question being graded.                         |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ASSIGNMENT     |              | ID of the quiz being graded.                             |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ROOT           |              | Absolute path to the working directory of the submission |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_RESULT         |              | Absolute path of the file where the grading script       |
|                      |              | writes the result (see "Results" below).                 |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ANSWER         | `answer.txt` | Name of the file where the student's answer is saved     |
| -------------------- | ------------ | -------------------------------------------------------- |
| CHALK_ANSWER_CONTENT |              | The student's answer itself, as text                     |
| -------------------- | ------------ | -------------------------------------------------------- |


Chalk also saves the same information in a file named `chalk.json`. The script
may choose the most convenient method to access this data. This is an example 
of a `chalk.json` file:

```json
{
  "course": "final-exam",
  "question": "q1",
  "student": "student-1",
  "root": "/path/to/course/final-exam/q1/grading-<timestamp>/student-1",
  "answer": "src/submission.py",
  "answer_content": "print('Hello, world!')\n"
}
```

> [!WARNING]
> A subtle difference between both approaches is that environment variables only
> support strings. The field "answer_content" may hold arbitrary JSON data depending
> on the type of submission. For example, a multiple selection question would 
> hold a list of selected string choices, a numerical question may hold a number 
> and so on. In most cases, we will use autograder to grade programming quizzes, 
> or some kind of text-based submission, so the difference is irrelevant.

## Results

The script writes the result to the file in `CHALK_RESULT`. The file is
created outside the working directory, so code started from the working
directory has no reason to touch it. Chalk detects the format from the
content:

- **Plain text.** The first line is the score and the other lines are the
  feedback shown to the student. The score may be a number (`0.8`), a
  percentage (`80%`) or a fraction (`3/4`).

  ```sh
  echo "3/4" > "$CHALK_RESULT"
  echo "The edge case x=0 is not handled." >> "$CHALK_RESULT"
  ```

- **JSON.** `{"score": 0.75, "feedback": "..."}`, `{"pass": 3, "fail": 1}`,
  or a report from `pytest-json-report`.
- **JUnit XML.** Any file that starts with `<`. The score is passed tests
  over passed plus failed plus errored ones; skipped tests do not count.
  The feedback lists the tests that did not pass. Most test runners write
  JUnit: `pytest --junit-xml="$CHALK_RESULT"`,
  `elm-test --report junit > "$CHALK_RESULT"`, jest with `jest-junit`,
  `cargo nextest`, `gotestsum`.

Chalk never reads the score from the script output. Standard output and
standard error go to the grading log (`chalk.stdout` in the working
directory), and a copy of the result is saved as `chalk.result`. A script
that writes no result file gets an error score.


## Limits

Every run has a timeout: `autograder.timeout` in `conf.yaml`, overridden by
`chalk autograde --timeout`, with a default of 30 seconds. When it expires,
chalk kills the script and every process it started.

Other limits go under `autograder.limits`. Sizes accept units such as
`512MB` or `1GiB`.

```yaml
questions:
  - id: q1
    autograder:
      timeout: 60
      limits:
        memory: 1GB        # address space of each process (RLIMIT_AS)
        file_size: 50MB    # largest file a process can write
        answer_size: 1MB   # larger text answers are rejected (default 1 MiB)
```

`memory` limits virtual memory, not resident memory. Node, the JVM and Go
reserve large virtual areas at startup, so give them a generous value or
leave `memory` unset.

The environment of the script only has `PATH`, `HOME`, the locale variables
and a few others. Add more with `autograder.pass_env`:

```yaml
    autograder:
      pass_env: [DATABASE_URL]
```


## Sandbox

Scripts run inside a [bubblewrap](https://github.com/containers/bubblewrap)
sandbox by default, so the student's code started by the script cannot read
your files, use the network or change the system:

- The whole file system is visible but read only. System packages and
  compilers work without configuration.
- `/home`, `/root`, `/run`, `/tmp`, `/var/tmp`, `/mnt`, `/media` and your
  home directory are replaced by empty directories. The directories in
  `PATH` and the Python that runs chalk are mounted back read only.
- The working directory and the result file are the only writable places.
- The network is off.

Options:

```yaml
    autograder:
      sandbox: bwrap         # default; "none" runs the script directly
      network: host          # default "none"
      mounts: [data, ~/.rustup]   # extra read only paths, relative to the question
```

Use `sandbox: none` only for scripts that read the answer without running
it (a regex, a string, code parsed without executing). A sandbox breaks a
script that needs files under hidden directories; list them in `mounts`.

Chalk fails with a message if `bwrap` is missing or the kernel does not
allow unprivileged user namespaces.

The sandbox protects your machine, not the grade: code that runs in the
same sandbox as the script can still write the result file.


## Regex answers

When the answer is a regular expression, the `regex` profile grades it
without a script. List the examples the answer must match and must not
match:

```yaml
questions:
  - id: q3
    type: text
    autograder:
      profile: regex
      regex_mode: full   # the whole example must match; "search" finds it anywhere
      match: [ana@unb.br, x.y@a.com]
      reject: ["@unb.br", "ana@"]
```

The score is the fraction of examples with the expected outcome, and the
feedback lists the others. The regex runs in a separate process with a
timeout of one second per example, so a regex with catastrophic
backtracking only fails the examples where it hangs.


## Python projects with pytest

The `python-pytest` profile grades a Python project with the tests of the
template, without a script. The score is the number of passed tests over
the number of tests in the template.

```
final-exam/
└── q1/
    ├── template/
    │   ├── pyproject.toml
    │   ├── uv.lock
    │   └── tests/
    │       └── test_calc.py
    └── solution/
        └── calc.py
```

```yaml
questions:
  - id: q1
    type: repo
    autograder:
      profile: python-pytest
      tests: [tests]     # default; test directories or files of the template
      timeout: 60
```

The template needs `pyproject.toml` and `uv.lock`, with pytest among the
dependencies (usually in the `dev` group). Grading has three steps:

1. **Prepare**, once per question. `uv sync --frozen` installs the template
   dependencies in a venv under `.chalk/cache/` in the classroom. The venv
   is reused until `pyproject.toml` or `uv.lock` change. Then the tests run
   on the template with `solution/`, in the sandbox, and the tests in that
   report are the expected tests. Without a solution, the template tests
   must run on their own.
2. **Test**, once per student, in the sandbox. The student's tests
   directory, `conftest.py` and pytest configuration files (`pytest.ini`,
   `pyproject.toml`, `tox.ini`, `setup.cfg`) are replaced by the
   template's, or removed when the template lacks them. The tests are
   mounted read only. Nothing from the student is installed: the project
   directory and `src/` go in `PYTHONPATH`, and the dependencies are the
   ones in the template lock file.
3. **Score**, in chalk. Only the expected tests count. A test missing from
   the report, failed, errored or skipped counts as a failure. Tests the
   student adds do not count.

Plugins are not loaded automatically (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`),
because the student could ship one. Load the plugins the tests need from the
template's `conftest.py`:

```python
pytest_plugins = ["pytest_asyncio"]
```

A test the template always skips counts as a failure for every student;
remove it from the template instead.

The tests import the student's code in the same process, so a determined
student can still tamper with pytest from inside it. The profile stops the
easy tricks (editing or deleting tests, a `conftest.py`, printing a fake
result) and keeps the output in `chalk.stdout` for review.

## Rust crates with cargo

The `rust-cargo` profile builds the student's crate and runs the
integration tests of the template (`tests/*.rs`) with
[cargo-nextest](https://nexte.st). Install it with
`cargo install cargo-nextest --locked`.

```
final-exam/
└── q2/
    ├── template/
    │   ├── Cargo.toml
    │   ├── Cargo.lock
    │   └── tests/
    │       └── calc.rs
    └── solution/
        └── src/
            └── lib.rs
```

```yaml
questions:
  - id: q2
    type: repo
    autograder:
      profile: rust-cargo
      timeout: 60              # test step
      build:
        timeout: 180           # build step, default 120
        limits:
          memory: 4GB
      on_build_error: manual   # build-error (default) | zero | manual
```

Steps:

1. **Prepare**, once per question. `cargo fetch --locked` downloads the
   dependencies of the template lock file to a cache under
   `.chalk/cache/`, separate from your `~/.cargo`. Then the template with
   `solution/` is built, and the result is kept as a cached target
   directory. The cache is reused until `Cargo.toml`, `Cargo.lock` or the
   compiler change. The build and test steps of the reference solution
   give the expected tests.
2. **Build**, once per student, in the sandbox and offline. The cached
   target directory is copied to the project (instantly on btrfs and xfs),
   so only the student's crate compiles.
3. **Test**, in the sandbox and offline, with `cargo nextest run`.
4. **Score**, as in python-pytest: only the expected tests count.

`Cargo.toml`, `Cargo.lock`, `.cargo/`, `.config/` and the test directories
come from the template, so the student cannot add dependencies, change the
build configuration or replace the test runner. A `build.rs` of the student
runs, but inside the sandbox. Unit tests inside `src/` do not count.

An answer that does not compile gets the `build-error` result, with the
compiler output as feedback. With `on_build_error: zero` it gets a zero
instead, and with `manual` it is left ungraded for `chalk grade`.

The toolchain is the one `rustc` selects in the template directory, so a
`rust-toolchain.toml` in the template is honored.

## Custom profiles

`python-pytest` and `rust-cargo` are written as data, in
[`chalk/autograder/profiles.toml`](https://github.com/fabiommendes/chalk/blob/main/chalk/autograder/profiles.toml).
A `[profiles.<name>]` table in `chalk.toml` adds a profile with the same
keys, for any test runner that writes a JUnit report. Questions select it
with `profile: <name>`.

```toml
# chalk.toml: each tests/*.sh of the template is a test of prog.sh
[profiles.shell-tests]
key = ["tests/inc.sh"]
build.command = "sh -n prog.sh"   # syntax errors are build errors
files."run.sh" = """
echo '<testsuites><testsuite>'
for t in tests/*.sh; do
  n=$(basename "$t" .sh)
  if sh "$t" >/dev/null 2>&1; then echo "<testcase classname='sh' name='$n'/>"
  else echo "<testcase classname='sh' name='$n'><failure/></testcase>"; fi
done
echo '</testsuite></testsuites>'
"""
test.command = 'sh {cache}/run.sh > "$CHALK_RESULT"'
```

With `extends`, a profile starts from another one and changes some keys.
Tables (`env`, `probe`, `files`, the steps) are merged key by key; other
values are replaced. A table with the name of a built-in profile replaces
it, and `extends` with its own name refers to the built-in one:

```toml
[profiles.python-pytest]
extends = "python-pytest"
env.PYTHONHASHSEED = "42"
```

| Key | Meaning |
| --- | --- |
| `key` | Template files the profile needs, such as lock files. Their contents select the cache. |
| `trusted` | Files and directories the template controls. The student's copies are replaced, or removed when the template lacks them. |
| `tests` | Default test directories or files (`["tests"]`). The `tests` option of a question overrides it. |
| `probe` | Variables set from the output of commands run outside the sandbox, such as the path of a toolchain. |
| `env` | Environment variables of every step. |
| `unset` | Environment variables removed in every step. |
| `readable` | Paths the sandbox mounts read only (default `["{cache}"]`). Needed for paths under hidden directories such as the home directory. |
| `files` | Files written to the cache: name and content. |
| `prepare.commands` | Commands that fill the cache, run once outside the sandbox and with the network on, in a copy of the template with the solution. |
| `build.command` | Optional build step. A failure is a build error. `build.seed` copies cache paths to the working directory first. |
| `test.command` | Test step. It writes a JUnit report to `$CHALK_RESULT`. |

Strings can use the variables `{cache}`, `{template}`, `{workdir}`,
`{tests}`, `{PATH}` and the probe names. Commands get them shell-quoted,
so `{cache}/run.sh` is safe with spaces. Unknown names such as `${HOME}`
are left for the shell.

The cache directory, `.chalk/cache/<profile>-<hash>`, is selected by the
contents of the `key` files, the probe output and the `probe`, `env`,
`unset`, `files` and `prepare` keys. Changing any of them prepares a new
cache. The tests and the solution are not part of it: the reference run
happens every time chalk grades.

The steps run with the environment described in [Sandbox](#sandbox):
`$HOME` and `/tmp` are empty, and the network is off except in `prepare`.

### Checking the autograder

Before grading the class, run the grader on the reference solution:

```sh
chalk autograde final-exam q1 --check
```

It grades `solution/` (or `answer_key.*` for text questions), shows the
feedback and exits with an error unless the score is 100%. It works with
any profile and with scripts.
