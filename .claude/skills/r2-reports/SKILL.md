---
name: r2-reports
description: Write a rich report for the human to read in the browser, by writing a Markdown file into .r2/reports/. Use when finishing a review, an analysis, a plan, a benchmark, or any piece of work whose result the human has to inspect, and while doing long work whose progress the human may want to watch.
---

# Writing r2 reports

Write a Markdown file to `.r2/reports/<name>.md`. That is the entire
interface. There is no command to run: a watcher notices the file and the human
sees the rendered page.

The human reads it in a browser where every path you mention becomes a link into
the file. Write reports for the human, not to remember things yourself.

## Reports are throwaway

`.r2/` is gitignored, and a report is meant to be read within minutes and
then forgotten. Write freely; you are not adding to an archive.

The corollary matters: **do not use a report to persist anything.** If something
needs to outlive today, say so and let the human decide where it goes, then write
an ordinary document in the repository. A handoff to a later session is persistent
by definition, so it is a real document, not a report.

## Writing one

```markdown
---
kind: review
title: Auth flow review
---

Three problems. The first one blocks the release.

```r2:finding severity=high ref=src/auth/session.py:40-58
The session token is not rotated on login, which allows session fixation.
```
```

Frontmatter is optional and every field in it is optional. `kind` is one of
`review`, `analysis`, `plan`, `summary`, `benchmark`, `memo`.

Mention the file path in your final message so the human can find it, or just say
what you wrote and where.

## Keep it current instead of writing a second one

Rewriting the same file updates the same report, live. For work that takes a while,
write the report early and keep it current as you go; the human watches it fill.
That is better than a burst of files, and it is better than saying nothing for ten
minutes.

An incomplete report is fine. A half-written sentence or an unterminated fence
renders as far as it goes and never shows an error.

## Reference code, never paste it

Write `src/auth/session.py:40-58`, not the lines themselves. The reference costs
you almost nothing, becomes a link to those lines, and reads the file as it is now.

Locators are the ones your tools already print:

```
src/auth/session.py         whole file
src/auth/session.py:45      one line
src/auth/session.py:45:7    line and column
src/auth/session.py:40-58   a range
```

You do not need link syntax in prose. A path written plainly is detected and
linked, and so are commit hashes:

```markdown
The failure is in src/auth/session.py:45. Introduced by a1b2c3d.
```

A detected path is linked only if it is a file on disk right now, so a wrong path
is silently not a link. Paths are relative to the repository root, with no `..`. The `ref` attribute
of a block is different: it is structured data, and a wrong ref there is an error.

## Blocks

Only these two. Anything else is prose.

`r2:finding` is one claim: `severity` is `high`, `medium`, `low` or `info`, and
`ref` is optional. One finding per problem; the human ticks them off one at a time,
so a finding that contains three problems cannot be ticked.

`r2:table` takes a JSON array of objects with consistent keys. For measurements,
not for prose in disguise.

There is no diff block. To point at a change, reference the lines.

## Length

A report is read by a human deciding whether to trust your work. Lead with what is
wrong or what you concluded. Put the reasoning under it. If it runs past a screen
and a half without findings, it is too long.

No preamble about what you are about to do, no summary of what you just wrote, no
restating the task.

## Details

`docs/reports.md` in the r2 repository is the full specification.
