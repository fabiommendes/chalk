---
name: r2
description: "Work in a repository managed by r2, the development assistant that keeps the project state in Markdown files (dev/, GLOSSARY.md, docs/user-stories). Use to prepare an existing repository for the r2 workflow (layout, AGENTS.md and the check command, glossary, decisions taken in the code, open work from GitHub and TODO comments, user stories), to build or update the project glossary and settle words used for the same concept, to record the decisions already in the code as ADRs, to look up project terms, or to brainstorm an idea that has no document yet into an RFC, an issue or a note, with fresh reviewers, or to triage the open defects and fix them with agents, unattended, ending in a report."
user-invocable: true
argument-hint: "[bootstrap · brainstorm · triage]"
---

r2 keeps the state of a project in files inside the repository and gives
humans and agents the same command line to read and change them. This skill
routes a request to the playbook of one area. Load only the playbook you need.

## Setup

1. Check that `r2` runs (`r2 help`). If it is missing, tell the human:
   `uv tool install "r2-assistant[tui,web]"`.
2. Read the "Language" section of `AGENTS.md`, if there is one: it says the
   language of each kind of document. Without it, write in the language the
   existing documents use.

## Commands

| Command | Use it to | Playbook |
|---|---|---|
| `bootstrap` | prepare an existing repository for r2: survey it, set up the layout, then run the commands below in order | [reference/bootstrap.md](reference/bootstrap.md) |
| `bootstrap-agents` | fill `AGENTS.md`: the check command (`r2 check`), the rules no tool checks, the standing orders | [reference/bootstrap-agents.md](reference/bootstrap-agents.md) |
| `bootstrap-glossary` | build `GLOSSARY.md` from the docs and the code, or update it, and settle synonyms | [reference/bootstrap-glossary.md](reference/bootstrap-glossary.md) |
| `bootstrap-modules` | write the missing package and module descriptions (docstrings or header comments) that `r2 modules` shows in the module map | [reference/bootstrap-modules.md](reference/bootstrap-modules.md) |
| `bootstrap-adrs` | record the decisions the code already embodies as ADRs, tied to the code by markers | [reference/bootstrap-adrs.md](reference/bootstrap-adrs.md) |
| `bootstrap-issues` | import the open work from GitHub issues and from TODO comments into `dev/issues/`, tied to the code by markers | [reference/bootstrap-issues.md](reference/bootstrap-issues.md) |
| `bootstrap-stories` | write the user stories of each role in `docs/user-stories/` and link them to the e2e tests that check them | [reference/bootstrap-stories.md](reference/bootstrap-stories.md) |
| `brainstorm` | turn an idea into an RFC, an issue or a note: questions, a brief, fresh reviewers (`r2 persona`) that attack it, and the items the human marked in `r2 web` | [reference/brainstorm.md](reference/brainstorm.md) |
| `triage` | triage the open defects and fix them unattended: confirm or reject the unconfirmed ones, fix the small and medium ones with TDD, plan the hard ones with goldfish and an advisor, and report; never asks the human | [reference/triage.md](reference/triage.md) |

Routing:

- **No argument:** list the commands above with one line each and ask which
  one to run. Never run one on your own.
- **Explicit or clearly implied command:** load its playbook and follow it.
- **A term or a question about the vocabulary:** answer with the commands of
  "Project vocabulary" below; no playbook.

## Rules for every command

- **Use the commands, not the editor, for state.** r2 writes the strict format
  of each file and takes the folder lock, so concurrent agents do not lose each
  other's changes.
- **Agent mode.** Run r2 with `R2_AGENT=1` in the environment or `r2 --agent`.
  It never prompts, and a destructive command needs `--yes`. Pass `--yes` only
  after the human approved that action in this conversation.
- **Markdown through stdin.** A text argument reads stdin when given `-`, so
  Markdown never fights shell quoting.
- **`--json`** on `list`, `show`, `find` and `check` gives data instead of
  text when you need to parse the result.
- **Ask with checkboxes.** When the human has to pick among several items, use
  the harness's structured question tool with multiple selection if there is
  one, in batches it accepts. Without one, write a numbered checklist
  (`- [ ] 1. ...`) and ask for the numbers to keep.
- `r2 <command> --help` has every option.

## Project vocabulary

| Command | Does |
|---|---|
| `r2 glossary show TERM` | the term's section |
| `r2 glossary find WORDS` | terms matching the words; a word to avoid prints `gadget -> Widget` |
| `r2 glossary list [--tag T]` | one line per term |

Before naming a new class, command, field or concept, run
`r2 glossary find` with the words you had in mind and use the term it gives
back. When the concept is new and belongs to the domain, propose a term to the
human instead of adding it silently.
