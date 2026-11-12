# bootstrap-issues

Gather the open work scattered in the issue tracker and in code comments into
`dev/issues/`, from the tracker first and the code second, so code comments
that repeat a tracker issue are recognized.

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first. Use the terms of `GLOSSARY.md`
in the titles and bodies; when there is no glossary, suggest running
`bootstrap-glossary` first.

Rules:

- **Ground everything in the repository.** Every issue cites the tracker
  entry or the places in the code it came from. Never write a requirement you
  did not find.
- **Propose, then write.** Create nothing the human did not keep.
- **Additive and safe to run again.** Read `r2 issue list` first and propose
  only work not recorded yet. Never rewrite or delete an existing issue, and
  never change the issue tracker.
- **Do not commit** unless the human asks.

Create each issue with `r2 issue new`, the body through stdin:

```sh
r2 issue new "Retry the upload on timeout" --kind defect --tag sync --body - <<'EOF'
...
EOF
```

## 1. From GitHub

Only when the remote is on GitHub and `gh` is authenticated:

```sh
gh issue list --state open --limit 1000 \
  --json number,title,body,labels,milestone,url,createdAt,author
```

Ask the human, before importing:

- which issues to bring: all, or a selection (offer to filter by label or
  milestone when there are many);
- what the tracker becomes afterwards: still the place for outside reports,
  with `dev/issues/` for the work, or closed to new issues. Record the answer
  in `AGENTS.md`, because agents need to know where to look for work.

Map each issue:

| GitHub | r2 |
|---|---|
| title | title |
| body | body, after a first line `Imported from <url>.` |
| label `bug` or similar | `--kind defect` |
| label `enhancement`, `feature` or similar | `--kind enhancement` |
| other labels | `--tag`, lowercase |
| a priority label | `--priority` |
| milestone | `--milestone` |
| author | `--by` |

Status is `backlog`: the human decides what is `todo`. Before creating, search
`dev/issues/` for the issue URL, so a second run does not import it again.
Comments on the GitHub issue stay there; the link reaches them.

## 2. From the code

```sh
git grep -n -E '\b(TODO|FIXME|XXX|HACK|BUG)\b' -- ':!*.lock' ':!*.min.*'
```

Add comments that admit a known limit without a marker: "not supported yet",
"temporary", "workaround", "for now". Skip generated and vendored code.

- **Group** the comments that point at the same piece of work into one
  candidate; one issue can cite several places.
- **Drop** the trivial ones (a missing docstring, a typo) and those that
  repeat an issue already in `dev/issues/` (from GitHub or a previous run);
  for the latter, record a marker for the existing issue.
- **Rank** by what breaks or blocks: `FIXME` and `BUG` before `TODO`, a
  comment on the main path before one in a script.

Show the candidates as a checkbox question: title, kind and the places
(`path:line`). Create each kept one in `backlog`, with the places cited in the
body as `path:line` and the quoted comment, and record a marker
`issue/<slug>` on each place (the line of the comment), as
[markers](markers.md) says.

## 3. Finish

1. Apply the markers as [markers](markers.md) says, unless this runs as a
   phase of `bootstrap`, which applies them once at its end.
2. `r2 roadmap` when the imported issues have milestones.
3. Summarize in a few lines: issues created by source, markers recorded,
   candidates turned down.
4. Propose a commit for the issues and another for the markers, and wait for
   the human.
