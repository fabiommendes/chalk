# bootstrap-adrs

Find the decisions the code already embodies and record the ones worth
keeping as ADRs in `dev/adr/`, each tied to the code by a marker.

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first. Use the terms of `GLOSSARY.md`
in the titles and bodies; when there is no glossary, suggest running
`bootstrap-glossary` first, and `bootstrap-modules` when packages have
no description.

Rules:

- **Ground everything in the repository.** Every ADR cites the files, commits
  or records it came from. Never write a reason or a date you did not find;
  write that it was not found and ask.
- **Propose, then write.** Create nothing the human did not keep.
- **Additive and safe to run again.** Read `r2 adr list` first and propose
  only decisions not recorded yet. Never rewrite or delete an existing ADR.
- **Do not commit** unless the human asks.

## 1. Find candidates

- The rules `bootstrap-modules` noted while describing the packages, and
  the package descriptions themselves (`r2 modules`).
- Decision records in another layout (`docs/adr/`, `docs/decisions/`,
  `doc/architecture/decisions/`, an "Architecture" or "Design" document).
  These are imported, not rediscovered: one ADR each, keeping the text and the
  original date.
- The stack: language, framework, database, main libraries (from the
  manifests). Keep only those with a visible alternative or a reason, such as a
  dependency replaced in the history or a library chosen over the common one.
- Boundaries: layers or packages that never import each other, a public API
  separated from the internals, a plugin mechanism.
- Formats and protocols: file formats, wire formats, storage layout,
  configuration format.
- Rules with a reason: comments that say "because", "instead of", "we
  don't", "never", "must"; `NOTE`, `WARNING` and `HACK` comments.
- The history: commit messages that switch, migrate, replace or revert
  something (`git log --format='%h %ad %s' --date=short` and search them).

A candidate becomes an ADR when a future reader, human or agent, could undo
it by accident, or would ask "why is it like this?". A choice local to one
function stays a code comment.

## 2. Settle with the human

Show the candidates as a checkbox question: one line each with the decision,
the evidence (`path:line`, commit hash) and whether the reason was found. If
there are many, show the 10 with the widest reach first. For a decision whose
reason was not found, ask for it in the same message; the human can answer
"unknown".

## 3. Write

For each kept candidate:

```sh
r2 adr new "Store the configuration as TOML" --tag config --body - <<'EOF'
...
EOF
r2 adr status <number> accepted
```

- `Context`: the problem, with the evidence cited as `path:line` or commit.
- `Options`: only the alternatives the evidence shows (a replaced library, a
  reverted approach). Leave out alternatives you would have considered.
- `Decision`: what the code does and the reason found. Without a reason, write
  "Reason not recorded." instead of guessing.
- `Consequences`: what the code shows it makes easier or harder.

The decision is already in place, so the ADR is `accepted`. When the date of
the decision is known (an imported record, the commit that introduced it),
set `decided` in the frontmatter to that date.

Right after creating each ADR, record a marker `adr-NNNN` (see
[markers](markers.md)) on the code that embodies the decision: the module,
class or function where a reader would ask "why?". One to three places per
ADR; a decision that touches the whole codebase gets none.

## 4. Finish

1. Apply the markers as [markers](markers.md) says, unless this runs as a
   phase of `bootstrap`, which applies them once at its end.
2. Summarize in a few lines: ADRs created (imported and found), markers
   recorded, candidates turned down.
3. Propose a commit for the ADRs and another for the markers, and wait for
   the human.
