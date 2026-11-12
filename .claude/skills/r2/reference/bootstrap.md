# bootstrap

Prepare an existing repository for the r2 workflow by running the bootstrap
commands in order. Each one is a playbook of its own and can also run alone;
this one only surveys the repository, sets up the layout, and runs the chosen
commands one after the other.

| Order | Phase | Playbook |
|---|---|---|
| 1 | layout and configuration | below |
| 2 | `AGENTS.md` and the check command | [bootstrap-agents](bootstrap-agents.md) |
| 3 | glossary | [bootstrap-glossary](bootstrap-glossary.md) |
| 4 | module descriptions | [bootstrap-modules](bootstrap-modules.md) |
| 5 | decisions in the code | [bootstrap-adrs](bootstrap-adrs.md) |
| 6 | open work, from GitHub and from the code | [bootstrap-issues](bootstrap-issues.md) |
| 7 | user stories and their e2e tests | [bootstrap-stories](bootstrap-stories.md) |
| 8 | markers | [markers](markers.md) |

`AGENTS.md` goes first because the later phases run the check command after
changing code. The glossary comes next because the later phases use its terms in the text
they write. The module descriptions come before the ADRs because reading each
package brings up the rules that become decisions. The stories come after the
issues, so a story not built yet can cite the issue that promises it.

Rules for the whole run:

- Each phase follows the rules of its playbook: grounded in the repository,
  proposed before written, additive and safe to run again.
- Markers are recorded during the phases and written into the code once, in
  phase 8, if the human agrees.
- **Do not commit** unless the human asks. Propose one commit per phase, so
  each can be reviewed or reverted on its own.
- **Leave the checks as you found them.** The run starts and ends by running
  the checks of the repository (step 0 and step 9). A failure that was not
  there at the start was caused by the run and is fixed before the commits
  are proposed.

## 0. Survey

Before changing anything, find out what applies:

- Is it a git repository? Is there a remote on GitHub (`git remote -v`), and
  does `gh auth status` succeed?
- Is r2 set up already: `r2.toml` or `[tool.r2]`, `dev/`, `GLOSSARY.md`,
  `AGENTS.md`? Is there a check command (`r2 check`, CI)? How many terms, ADRs and issues are there?
- Are there decision records in another layout (`docs/adr/`,
  `docs/decisions/`, `doc/architecture/decisions/`)?
- How many packages have no description (`r2 modules --missing`)?
- How many `TODO`/`FIXME` comments are there, roughly?
- Are there user stories (`r2 story list`) and e2e tests, and where?

Then record the baseline, before any change:

```sh
r2 test
r2 check            # when the project declares it
```

When `r2 check` does not exist yet, run what CI runs (lint, types, tests).
Note every failure as known: the run did not cause it. Check also that
`r2 test` finds and runs the real suite (the same tests CI runs, not zero
tests nor the wrong runner); when it does not, report it to the human as an
r2 problem. Show the baseline with the survey.

Show the human the phases with what each would do in this repository (skip
the ones that do not apply, saying why), and ask which to run, as a checkbox
question. Run the chosen ones in order. Load the playbook of a phase only when
its turn comes, and skip its own finishing steps that this playbook does at
the end (applying markers, proposing commits).

## 1. Layout and configuration

```sh
r2 init
```

It creates only what is missing and prints each path: the `dev/` folders, a
skeleton `AGENTS.md` (with `CLAUDE.md` as a link, unless there is already a
`CLAUDE.md`), an empty `GLOSSARY.md`, agent mode in `.claude/settings.json`,
`r2.toml` and `.r2/`.

Then settle the language of the documents, because every later phase writes
them. If `AGENTS.md` has no "Language" section, look at the language of the
existing docs, comments and commit messages, propose one (for example: code,
comments and user docs in English; `dev/` in Portuguese), and ask the human.
Write the answer as a "Language" section in `AGENTS.md`.

## 2. AGENTS.md and the check command

Run [bootstrap-agents](bootstrap-agents.md).

## 3. Glossary

Run [bootstrap-glossary](bootstrap-glossary.md).

## 4. Module descriptions

Run [bootstrap-modules](bootstrap-modules.md).

## 5. Decisions in the code

Run [bootstrap-adrs](bootstrap-adrs.md), starting from the rules phase 4
noted as ADR candidates.

## 6. Open work

Run [bootstrap-issues](bootstrap-issues.md).

## 7. User stories

Run [bootstrap-stories](bootstrap-stories.md).

## 8. Markers

Apply the markers recorded by the earlier phases, as [markers](markers.md)
says.

## 9. Finish

1. Run the baseline again (`r2 test`, `r2 check`) and compare: any failure
   not in the baseline is fixed now, or reported to the human if it cannot
   be. Then `r2 glossary check`, `r2 story check`; `r2 roadmap` when the
   imported issues have milestones.
2. Summarize in a few lines: the baseline and the final checks, files
   created by `r2 init`, the check command, glossary terms, ADRs,
   package descriptions, issues by source, stories by role, markers written, and what was skipped and why.
3. Propose the commits, one per phase, and wait for the human.
