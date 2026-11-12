# triage

Triage the open defects of the project and fix what agents can fix alone:
confirm or reject the unconfirmed ones, check the ones in progress, fix the
small and medium ones with TDD, plan and fix the hard ones with goldfish
reviewers, and end with a report for the human.

Run it only when the human asks for it. It starts many Opus and Sonnet
subagents and can cost a few million tokens on a large backlog.

Requires the r2 layout (`r2.toml` or `[tool.r2]`) and a check command in
`AGENTS.md`. Without the layout, stop and point to the
[bootstrap](bootstrap.md) playbook. Without a check command, run phase 1
only and say in the report that nothing was fixed because nothing can be
verified.

## Autonomy

The whole run is autonomous. Never ask the human anything, never wait for a
mark, never stop for a confirmation. When a choice comes up, take it, and if
it is not obvious, write it in the report. Asking the human for this command
is their approval for everything below:

- changing the status of the issues in scope and commenting on them;
- creating the triage branch and its worktree, committing to it, and merging
  it into the base branch under the rule of phase 5;
- passing `--yes` to the r2 commands this playbook runs.

It is not approval for anything else: never push, never change a remote
(GitHub issues, pull requests), never rewrite history, never touch the
human's uncommitted work.

## Roles

- **You** are the elephant and the orchestrator: you hold the run, read every
  result and write the report. Delegate the investigation and the code. Your
  context must hold only conclusions.
- **Verifiers** check one issue each in phase 1. Use the project's
  `investigator` agent if there is one; otherwise a general-purpose
  subagent with a Sonnet-class model.
- **The advisor** is one general-purpose subagent with an Opus-class model,
  started at the beginning of phase 2 and kept alive with `SendMessage` until
  the end of phase 4. It classifies, reviews commits, mediates and decides.
  It reads and runs read-only commands; it never edits.
- **Implementers and testers** write the code under the `tdd` skill. Use the
  project's `implementer` and `tester` agents if they exist; otherwise
  general-purpose subagents with the briefs of the `tdd` skill and a
  Sonnet-class model.
- **Goldfish** are fresh reviewers from `r2 persona`, started with the
  persona's prompt and nothing else (see the [brainstorm](brainstorm.md)
  playbook for why).

If you cannot start subagents, stop and tell the human. This playbook does
not work in a single context.

## Setup

1. The base branch is the branch checked out now. Create the branch
   `triage/<YYYY-MM-DD>` from it (add `-2`, `-3` if it exists) in a new git
   worktree, at the path `AGENTS.md` gives for worktrees, or else at
   `../<repo>.triage-<YYYY-MM-DD>`. All the work, the r2 commands
   included, runs in that worktree, so the status changes travel with the
   code and the human's uncommitted work in the main checkout stays out.
2. The report is `.r2/reports/triage/<YYYY-MM-DD>.md` in the **main
   checkout**, where `r2 web` shows it. Use the `r2-reports` skill, with
   `kind: summary`. Write it now with the section headings and keep it
   current after each phase: the human may watch it fill.
3. Write the report in the language the "Language" section of `AGENTS.md`
   sets for `dev/` documents, and the comments in the language of the issues.

## Dependencies

An issue lists in `blocks` the slugs of the issues that wait for it. So
the blockers of an issue X are the open issues whose `blocks` contains X.
A closed blocker (`completed`, `wont_fix`, `deprecated`) no longer blocks.

Build the graph in phase 1, from every open issue (`r2 issue list --json`,
`meta.blocks`), not only the defects in scope. Keep it current through the
run, and apply these rules:

- **Do not implement an issue whose blocker stays open.** A blocker outside
  the run (an enhancement, an issue this run will not fix) keeps its
  dependents out: they stay as they are, with a comment naming the blocker,
  and the report lists them.
- **Order by the graph.** Within a phase, a blocker goes before what it
  blocks, even across themes. If a blocker fails or is left out, its
  dependents in the run are skipped with a comment naming it.
- **Unblock.** When the last open blocker of a `blocked` issue is fixed in
  the branch, found done in phase 1, or closed as `wont_fix` there, move the issue to
  `todo` with a comment citing the commit or the blocker. If it is a
  defect, it joins the run: the advisor classifies it, and it goes to the
  phase of its class, or to the current phase if that one has passed. Any
  other kind only moves to `todo`.
- **Dependencies found on the way.** A verifier, the advisor or an
  implementer may find a dependency the `blocks` fields do not declare. Treat
  it as declared for the run, comment it on both issues, and list it in
  the report. r2 has no command that sets `blocks`, so do not edit the
  frontmatter by hand: the human records it.
- **Cycles.** Send the cycle to the advisor, which picks the issue to do
  first, or leaves the whole cycle out for the human.

## Phase 1: triage

Collect the defects in scope, and the `blocked` issues of any kind, which
only the graph can release:

```sh
r2 issue list --kind defect --status backlog --status todo --status in_progress --json
r2 issue list --status blocked --json
```

Then build the dependency graph (see [Dependencies](#dependencies)).

Start one verifier per issue in `backlog` and in `in_progress`, in parallel,
in batches of up to 5. Each gets the issue path and the job below, and
returns a verdict with evidence: commands run with their output, `path:line`
references, a failing test. A verdict without evidence is not a verdict;
send the verifier back once, and if it still has none, treat the issue as
not confirmed for `backlog` and as unfinished for `in_progress`.

**Backlog** (an unconfirmed defect): reproduce it on the current code.

- Confirmed: comment the reproduction on the issue
  (`r2 issue comment ID -`) and move it to `todo`.
- Not confirmed: comment the evidence that the defect does not happen, or
  no longer happens (and since when, if `git log` shows it), and move it to
  `wont_fix`.

**In progress**: check whether the work the issue describes is done.

- If the issue tracks progress with GFM checkboxes (`- [ ]`), only fix the
  boxes so they match the code: tick what is done, untick what is not. No
  comment.
- Otherwise, if the work is not done, comment what is still missing, as a
  short checklist.
- Done: the issue goes straight to phase 5. It skips phases 2 and 3.

Issues in `todo` need no verifier: they enter phase 2 as they are.

Commit the phase 1 changes to the issues in one commit.

Report, section `## Issues`: the links to the issues (the `dev/issues/...`
path is enough), no descriptions. When the issues fall into themes, one
`###` subheading per theme. The `wont_fix` issues go in their own
subheading, last.

## Phase 2: small defects

1. Start the advisor. Its first job: classify every issue in `todo` and
   group them into the themes of phase 1. One class per issue:

   | Class | Scope |
   |---|---|
   | trivial | limited and local |
   | low | one module, no architectural refactoring |
   | medium | small structural refactorings in a few modules, or light design with essentially additive changes |
   | high | needs design and changes the architecture or behavior deeply |

   Send it the dependency graph too, and ask it to point out dependencies
   the graph misses. Read the classification and challenge any item you
   disagree with, once. The advisor has the last word.

2. One plan per theme, in the order of the themes, except where the graph
   puts a blocker of another theme first. Within a theme:
   - **Trivial and low:** one implementer subagent, which follows the `tdd`
     skill in `lite` mode. It commits, grouping related issues in one
     commit, and adds a regression test wherever the defect could come back
     unnoticed. It may skip the test only for a change no test can observe
     (a typo in a message, a comment), and says so in the commit message.
   - **Medium:** the `tdd` skill in `full` mode: a tester and an
     implementer, with you as the orchestrator. Same rules for commits and
     regression tests.

3. Every commit passes the check command before it is made. A batch that
   cannot pass is reverted, its issues go back to `todo` with a comment on
   what was tried and what failed, and the run goes on. Never commit red.

4. After each commit, send its hash to the advisor for review. A review that
   asks for changes goes back to the same implementer; after two rounds, the
   advisor decides whether the commit stays or is reverted.

5. Each fixed issue moves to `in_review` for now, with a comment citing the
   commit. Phase 5 decides its final status.

Report, section `## Small defects`: a short summary that highlights only an
unexpected obstacle or an important discovery made while fixing. When there
is none, one sentence is enough: "Every trivial, low and medium issue was
fixed without obstacles."

## Phase 3: hard defects

The issues the advisor classified as high, one at a time, in theme order
with blockers first. When the budget below will not reach every issue, pick
first the ones that unblock others.

### Context budget

Before each issue, measure your own context. In Claude Code:

```sh
f=$(ls ~/.claude/projects/*/"$CLAUDE_CODE_SESSION_ID".jsonl 2>/dev/null | head -1)
tac "$f" | jq -r 'select(.type=="assistant" and .message.usage) | .message.usage
  | .input_tokens + .cache_read_input_tokens + .cache_creation_input_tokens' | head -1
```

Stop the loop at 250k tokens, or when the harness warns that it is about to
compact the conversation. Without the variable or the file (another
harness), stop after 3 hard issues. The remaining issues stay in `todo`;
the report says which ones were left out and why.

### For each issue

1. **Proposal.** Write the approach in general terms: the cause, the idea of
   the fix, what it changes and what it leaves alone. Save it as
   `.r2/reports/triage/<slug>.md`, in the brief format of the
   [brainstorm](brainstorm.md) playbook, and comment it on the issue.
2. **Goldfish.** Two personas, by what the issue touches:

   | The issue touches | Personas |
   |---|---|
   | default | `architecture`, `breaker` |
   | UI or CLI surface | `architecture`, `ux` |
   | file format or persisted data | `architecture`, `compat` |
   | performance | `architecture`, `cost` |

   For each, run
   `r2 persona show NAME --mode brainstorm --input .r2/reports/triage/<slug>.md --report .r2/reports/triage/<slug>/NAME.md`
   and start a fresh subagent with that output, verbatim, as the whole prompt
   and the persona's model. Both in parallel. Then comment each report's
   conclusion on the issue (`r2 issue comment ID - --by NAME`).
3. **Consensus.** If both goldfish accept the proposal, or ask only for
   changes you adopt, it is settled. Otherwise send the proposal and the two
   reports to the advisor to mediate a round: revise the proposal, comment
   the revision, and run the goldfish again on it. After two rounds without
   consensus, the advisor decides the approach. Comment the final approach
   on the issue, saying who decided.
4. **Implementation.** The `tdd` skill in `default` mode, or `full` when the
   change spans several modules or the tests are laborious. The commit,
   check and advisor review rules of phase 2 apply.

## Phase 4: final report

Add to the report:

- One `###` section per hard issue, under `## Hard defects`: the approach
  taken in two or three lines, and the commits. Say it explicitly when an
  issue was not fixed, and why (context budget, check failing, no
  consensus worth implementing).
- `## Dependencies`, only when the run touched the graph: a table with the
  issues it unblocked, the ones left out because of an open blocker, and
  the dependencies it found that `blocks` does not declare yet.
- `## Manual validation`: what the human must check, as a checklist of short
  items with `path:line` references or screenshots. Business decisions that
  are not obvious, the look of a screen, a result that needs a human eye.
  Leave the section out if there is nothing.

The report must be quick to inspect: tables, short checklists, images.
Avoid long descriptive paragraphs, long lists and algorithm details.

Then have two goldfish review the report: `comprehension` (can someone who
was not in the run follow it?) and `skeptic` (what does it claim as fixed
that is not?). Same consensus process as in phase 3: you revise, the
advisor mediates, and after two rounds the advisor decides.

## Phase 5: close

For each issue the run worked on, decide from the report:

- `completed`: the fix is in and nothing in it needs the human.
- `in_review`: only when an item of `## Manual validation` depends on it.

Commit the status changes. Then merge:

- **No issue in `in_review`:** merge the triage branch into the base
  branch in the main checkout and remove the worktree. If the merge
  conflicts with the human's uncommitted work, or the base branch moved and
  the merge conflicts, abort it and keep the branch.
- **Otherwise:** keep the branch and the worktree for the human to review.

End the report with the branch, whether it was merged, and the cost of the
run (the subagents' token totals). In the chat: the path of the report and
one line on the result.
