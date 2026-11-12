# bootstrap-agents

Fill `AGENTS.md`, the rules every agent reads before working in the
repository: what the project is, the commands, the conventions no tool
checks, and what an agent may do without asking. `r2 init` writes a skeleton
with these sections; this playbook fills it from the repository.

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first.

Rules:

- **Only what the code does not show.** `AGENTS.md` is read by every agent in
  every session, so each line costs. Leave out what an agent finds by reading
  the code, the manifests or `r2 context` (the folder layout, the stack, the
  module map).
- **A rule a tool can check goes to the tool.** Propose a lint rule, a test or
  a pre-commit hook instead of a sentence, and write the sentence only when no
  tool fits.
- **Propose, then write.** Keep what is already in `AGENTS.md` (or
  `CLAUDE.md`, when it is the real file); add only what is missing.
- **Do not commit** unless the human asks.

## 1. The project

One or two sentences under the title: what the project is and who uses it,
from the README. Skip it when the README says it in its first lines and
`AGENTS.md` points to it.

## 2. The check command

The one command that says a change is done: tests, lint and types together
(ADR 0003 of the method). Find the pieces in the manifests (`pyproject.toml`,
`package.json` scripts, `Cargo.toml`, `Makefile`, `justfile`, `noxfile.py`,
`tox.ini`), the CI workflows (`.github/workflows/`) and the pre-commit
configuration. CI is the best evidence: it is what the project already
trusts.

Declare it as a project command in `r2.toml`, so every repository has the
same entry point, `r2 check`:

```toml
[commands.check]
run = "uv run ruff check && uv run mypy . && uv run pytest -q"
help = "Tests, lint and types: the change is done when this passes."
```

Run `r2 check` once. When it fails on the current code, show the failures and
ask the human whether the command is right and the code is broken, or the
command is wrong. Never weaken the command so it passes.

When there is no lint or type checker, say so and propose one; adding it is
an issue (`r2 issue new ... --kind task`), not part of this run.

List under `## Commands` the check command and the few others an agent needs:
how to run one test, how to run the project locally, how to format. One line
each, the command first.

## 3. Rules

Conventions no tool checks, found in:

- `CONTRIBUTING.md`, the README, a style guide in `docs/`;
- the review comments of merged pull requests, when the remote is on GitHub
  (`gh pr list --state merged --limit 30 --json number` and
  `gh api repos/{owner}/{repo}/pulls/N/comments`): what reviewers ask for
  again and again;
- the history: commits that revert or fix the same kind of mistake;
- the code: patterns every module follows that a newcomer would break (how
  errors are raised, where I/O happens, how modules are named).

For each candidate, ask first whether a tool could check it; if so, propose
the tool. Show the rest as a checkbox question, one line each with the rule
and the evidence. A rule says what to do and, in a few words, why, when the
reason is not obvious. A rule that records a design decision with a story
behind it is an ADR (`bootstrap-adrs`), and the rule cites it.

## 4. Standing orders

Maintenance an agent may do without an approved issue, such as updating
dependencies, fixing lint warnings, or regenerating a generated file. Ask the
human, with a checkbox question of the ones that apply to this repository,
plus the option of none. Write each as one line with its limit ("patch and
minor versions only").

## 5. Write

Edit `AGENTS.md` with the editor, section by section, in the language the
"Language" section declares. Drop the placeholder text of the skeleton, and
any skeleton section left empty.

## 6. Finish

1. Run `r2 check` again if the command changed.
2. Summarize in a few lines: the check command and whether it passes, rules
   added, rules turned into tool proposals, standing orders.
3. Propose one commit for `AGENTS.md` and `r2.toml`, and wait for the human.
