# bootstrap-stories

Write the user stories of the product in `docs/user-stories/<role>.md`: who
uses it, what each of them gets done with it, and which e2e test checks each
story. The stories are the contract between what the product promises and
what the tests check; `r2 story check` keeps the two in step.

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first. Use the terms of `GLOSSARY.md`
in the titles and narratives; when there is no glossary, suggest running
`bootstrap-glossary` first.

Rules:

- **Ground everything in the repository.** A story comes from what the
  documents promise or what the code does: a page, a route, a CLI command, an
  e2e test. Never invent a feature.
- **The status tells the truth.** `implemented` when the code does it,
  `partial` when it does part of it, `todo` when only a document or an issue
  promises it. A story without a test stays as it is: the missing test is what
  `r2 story check` reports.
- **Propose, then write.** Create nothing the human did not keep.
- **Additive and safe to run again.** Read `r2 story list` first and propose
  only stories not written yet. Never rewrite or remove an existing story.
- **Do not commit** unless the human asks.

## 1. Survey

```sh
r2 story list
r2 story check
```

`r2 story check` reads the e2e tests from one place: `test/stories` or
`tests/stories` by default, or the files and folders in
`[config.stories] tests`. It treats every test there as an e2e test and
reports each one that cites no story. So that place must hold e2e tests only,
never the unit tests.

Find the e2e tests: Playwright, Cypress or vitest browser tests, pytest tests
that drive the CLI or the HTTP API end to end. Note where they are:

- in `tests/stories` (or `test/stories`): nothing to configure;
- in folders or files of their own (`e2e/`, `tests/test_e2e.py`): list exactly
  those in `[config.stories] tests` in step 6;
- mixed with unit tests in the same files or folder: never point
  `[config.stories] tests` at that folder. Propose moving the e2e tests to
  `tests/stories/`, and do it in step 6 only if the human agrees;
- none: there is nothing to link; the stories stay without tests.

Note their titles; each is a candidate story, and they are linked in step 6.

## 2. The roles

A role is a kind of person who uses the product with its own goals and
permissions: `student`, `instructor`, `admin`. Find them in:

- the documents (README, `docs/`, the glossary);
- the code: user roles and permissions, separate areas of the UI or the API,
  the commands for operators (migrations, backups);
- for a library or a developer tool, the developer who uses it, and the one
  who extends it (writes a plugin) when the docs talk to both.

Most products have one to four roles. Show them as a checkbox question, with
one line each saying who it is and where you found it. The role name is the
file name and the prefix of every story id, so keep it a short lowercase noun.

## 3. Find the stories

For each kept role, list what it gets done with the product, from:

- the documents: usage sections, tutorials, guides, the CLI help;
- the code the role reaches: pages and their routes, API endpoints, CLI
  commands and their options, background jobs the role starts;
- the e2e tests, by their titles;
- the open issues, for `todo` stories, only when an issue describes a goal of
  the role and not a fix.

A story is one goal the role reaches from start to end, in its own words:
`Log in`, `Import a term's calendar`, `Reset a password for someone locked
out`. Not a function, a screen or an endpoint: one story often uses several,
and one endpoint often serves several stories. The title starts with a verb
and makes sense after "I want to".

Group the stories of a role in sections (level 2 headings) by area of the
product, following the tags of the glossary when there are any. A first pass
usually has 5 to 25 stories per role.

## 4. Settle with the human

Per role, show the stories as checkbox questions, one question per section:
title, status and evidence (`path`, route or command). Ask in the same
message about the stories whose status you are unsure of.

## 5. Write

Create each kept story, with the narrative through stdin:

```sh
r2 story new "student: Log in" --section "Joining the platform" \
  --status implemented --url /login --body - <<'EOF'
Student has an account from an invite and wants to reach their courses. They
sign in with their email and password and land on the course list.
EOF
```

- The narrative says what the role wants, what it does and what it ends
  with, in two to five sentences. It does not describe the UI element by
  element.
- `--url` only when the story happens on one page or one endpoint.
- `--relatedTo` the issues and ADRs the story depends on: a `todo` story
  cites the issue that promises it.

`r2 story new` creates the file of the role. Write the introduction of the
file (who the role is and what it can do) with the editor, under the level 1
title, then run `r2 story fmt`.

## 6. Link the e2e tests

A test cites a story by its id, and r2 reads the citation without running the
tests:

| Runner | Citation |
|---|---|
| vitest, Playwright | the test title is the story: `test("student: log in", ...)` |
| pytest | `@pytest.mark.story("student: log in")` on the test or its class |

When the e2e tests are in their own files or folders outside
`tests/stories`, list them, and only them, in the manifest (see step 1):

```toml
[config.stories]
tests = ["e2e", "tests/test_cli_e2e.py"]
```

Never list the whole test folder (`tests = ["tests"]`): every unit test would
show up as a test that cites no story.

Match each existing e2e test to the story it checks, and show the pairs as a
checkbox question. Adding a citation changes test code (a renamed title, a
new marker), so do it only for the pairs the human kept. With pytest and
`--strict-markers`, register the `story` marker in the pytest configuration.

Run `r2 story check`. What it still reports is the coverage gap: stories
without a test, tests that cite no story. Leave it as it is, or open one issue
for the missing tests (`r2 issue new ... --kind task`) if the human wants.

## 7. Finish

1. `r2 story check` and `r2 story fmt`.
2. Summarize in a few lines: roles, stories by status, tests linked, stories
   still without a test.
3. Propose a commit for the stories and another for the test citations, and
   wait for the human.
