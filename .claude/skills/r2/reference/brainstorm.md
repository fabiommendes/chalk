# brainstorm

Turn a raw idea into an RFC, an issue or a note: question the human until the
problem is clear, write a brief, have fresh goldfish reviewers
(`r2 persona`) attack it, and write the output from the items the human
marked in `r2 web`.

Run it only when the human asks for it: each round starts one Opus
subagent per persona, a few hundred thousand tokens in all.

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first.

You are the elephant: you hold the whole conversation. The goldfish are
reviewers started fresh for one task, with no history: they see only the
brief and the repository. That is the point. Whatever the brief does not say,
they cannot guess, and the gaps they find are the gaps a new reader would
find.

The flow: questions, hypothesis, brief, goldfish, consolidation, marks,
output. Do not skip a step and do not reorder them.

## Rules for the whole conversation

- Critique first. Before agreeing with anything, look for the weakest point,
  the case that breaks it and the cheaper way that already exists. No
  compliments, no apologies: when corrected, state the corrected reasoning.
- Do not repeat the human's framing back as a conclusion. If they assert
  something, check it against the repository.
- Plain language. No promotional adjectives.
- Never paste the brief into the chat. It lives in a file; point to it.
- Write `dev/` documents and the brief in the language the "Language"
  section of `AGENTS.md` sets for them; without one, in the language the
  existing documents use.

## 1. Context

Run `r2 context` and read it: the terms, the ADRs in force, the open work.
If the human points to an existing note or issue, read it with
`r2 note show ID` or `r2 issue show ID`. An idea that an open RFC or issue
already covers is not a new brainstorm: say so and stop unless the human
insists.

## 2. Questions

Ask open questions in plain chat, one or two per turn. No multiple-choice
options and no question tool here, despite the router's rule on
checkboxes: offered answers steer the human. Cover:

- What problem, for whom? How is it handled today, and why is that not good
  enough?
- What are the hard constraints?
- What is out of scope?
- How will we know it worked?

Keep asking until you could explain the problem and its boundaries to
someone who was not here. That usually takes several turns. Do not start
the goldfish on a single answer.

## 3. Hypothesis

Write the working hypothesis in two or three sentences: the idea, for whom,
and the main boundary. Show it in the chat with the review level and the
personas it runs (`r2 persona list --mode brainstorm` lists them for the
project's default level; `--level lite|medium|full` for another). Ask the
human to confirm the hypothesis and the level, or to correct them.

Go on only after the human confirms. A correction means a new hypothesis
and a new confirmation.

## 4. The brief

Pick a short kebab-case slug for the idea. The brief is
`.r2/reports/brainstorm/<slug>.md`; if that file exists, use `<slug>-2.md`,
`<slug>-3.md` and so on. Write it before any goldfish runs: they read it.

The brief is an r2 report (see the `r2-reports` skill). Each item is its own
`r2:finding` block with `severity=info`, so the human can accept or reject
it alone. A block with three goals cannot be accepted by half.

````markdown
---
kind: memo
title: <the idea, as a title>
---

<The confirmed hypothesis, as the opening paragraph, without a heading.>

## Goals

```r2:finding severity=info
<one goal>
```

## Non-goals

```r2:finding severity=info
<one thing left out, and why>
```

## Alternatives weighed

```r2:finding severity=info
<one option the discussion dropped, and the reason>
```

## Decisions

```r2:finding severity=info
<one choice the discussion already made>
```

## Open questions

<Plain text, no blocks: there is nothing to mark.>
````

Only what the conversation said. A section with nothing in it stays out.
Do not put fenced code inside an `r2:finding` block.

## 5. Goldfish

1. `r2 persona list --mode brainstorm --level L --json`, with the level the
   human confirmed. Each item has `name` and `model`.
2. For each persona, run
   `r2 persona show NAME --mode brainstorm --input .r2/reports/brainstorm/<slug>.md`.
   Its output is the whole prompt of that goldfish.
3. Start one fresh general-purpose subagent per persona, all in parallel,
   with that output as the prompt, verbatim, and the persona's `model`. Add
   nothing: no summary of the conversation, no hint of what you expect. A
   goldfish that knows what you think is no longer a goldfish.
4. Each goldfish writes `.r2/reports/brainstorm/<slug>/<name>.md`. Wait for
   all of them. Do not edit the brief while they run.

If you cannot start subagents, stop and tell the human. A review in your own
context is not a goldfish review.

## 6. Consolidation

Read every report. Then rewrite the brief, adding an `## Analysis` section
after the opening paragraph:

- One `r2:finding` block per distinct problem, with the severity and the
  `ref` the goldfish gave. When several goldfish raised the same problem,
  merge them into one block and keep the highest severity.
- End each block with the personas that raised it, as `Raised by: skeptic,
  ux.`
- Highest severity first.
- Keep what the goldfish said. Do not soften a finding, and do not drop one
  because you disagree with it: say why in the block and let the human mark
  it.
- A persona that wrote no report, or a report that does not parse, is a line
  in the Analysis: `No report from <name>.` Silence is not approval.

Do not change Goals, Non-goals, Alternatives or Decisions on the strength of
a finding. That is the human's call, made by marking.

In the chat: the path of the brief, the two or three findings that most
threaten the idea, one line each, and the next step: open the brief in
`r2 web` (`r2 web open`) and mark every block as accepted or rejected, with
a note where the reason is not obvious, or tell you what to change.

## 7. Changes and new rounds

The marks live in `.r2/reports/brainstorm/<slug>.review.json`, keyed by the
order of the blocks in the brief (`f1`, `f2`...). Editing the brief after
any mark shifts the keys and attaches the human's marks to the wrong items.

- No `.review.json` yet: you may edit the brief in place when the human
  asks for a change in the chat.
- A `.review.json` exists: never edit the brief again. A change is a new
  round.
- A change that needs the goldfish again is always a new round.

A new round is a new brief, `<slug>-2.md`, from step 3: a new hypothesis to
confirm, then the brief and the goldfish. What the earlier round settled
goes into the new brief as items again, so the human can mark them in one
place.

## 8. Reading the marks

When the human says the brief is marked, read the `.review.json` and count
the `r2:finding` blocks in the brief. The brief is reviewed only when the
file exists and every key from `f1` to `fN` has the state `accepted` or
`rejected`. `seen` is not a mark.

A missing file or an unmarked block means the human has not finished, not
that nothing was rejected. List the unmarked items by their first line and
ask. Do not write the output until every item has a mark, unless the human
tells you to treat the unmarked ones in a given way; then say how you
treated them in the output's comment.

## 9. Output

Ask the human which output fits, with your recommendation:

- **RFC** (`r2 rfc new TITLE --body -`): a design with choices that others
  should review. The usual output.
- **Issue** (`r2 issue new TITLE --body -`, status `backlog`): the change is
  small and the brainstorm settled the design.
- **Note** (`r2 note new TITLE --kind idea --body -`): the idea is not
  ready; park it with what was learned.

Where each marked item goes:

| Item | Accepted | Rejected |
| --- | --- | --- |
| goal | `Problem` or `Proposal` | dropped |
| non-goal | `Proposal`, as out of scope | dropped |
| alternative weighed | `Alternatives` | back to discussion: the human wants it considered |
| decision | `Proposal` | `Alternatives`, with the reason |
| analysis finding | the `Proposal` addresses it, or it goes to `Open questions` | dropped |

For an issue or a note, use the same split in their own sections. A
rejected alternative reopens a question: raise it in the chat before
writing, or put it in `Open questions` if the human prefers.

The output does not cite the brief: the brief is a report and disappears.
After creating it, add a comment
(`r2 rfc comment ID -`, or `issue`/`note`) that records what the human
accepted and rejected in the brief, one line per item, with the note of
each mark. The comment stays when the report is gone.

Tell the human the path of the new document. For an RFC, the next step is
its own review; it starts as `draft`.
