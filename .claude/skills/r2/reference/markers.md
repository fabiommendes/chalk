# Markers

A marker is a comment that ties code to the documents about it, so a reader of
the code finds the decision or the open work, and a reader of the document
finds the code:

```python
# r2: adr-0003, issue/retry-on-timeout
class RetryPolicy: ...
```

The comment uses the syntax of the file's language. A reference is
`adr-NNNN`, `issue/<slug>`, `rfc/<slug>` or `spec/<slug>`; the script also takes
`adr/NNNN` and writes it as `adr-NNNN`.

Never insert markers with the editor, one by one: each insertion shifts the
lines of the next ones in the same file. Use the helper script,
`<skill-dir>/scripts/markers.py`, where `<skill-dir>` is the folder of this
skill's `SKILL.md`. It needs only Python 3 and runs from anywhere in the
repository.

## Record

While working, right after creating a document the human kept:

```sh
python3 <skill-dir>/scripts/markers.py add PATH LINE REF...
```

It checks that the document exists and records the marker against the line
and its text in `.r2/markers.json`. Point at the first line of the code the
marker is about (the `class` or `def` line, the comment line), never a blank
one. Record markers only for the documents the human kept; the markers follow
from that choice and are not validated one by one.

## Apply

Once, at the end of the run (at the end of `bootstrap` when the command runs
as one of its phases):

- Ask the human one question: write the markers into the code or not. Say how
  many markers and files it touches (`markers.py list`). On no, leave
  `.r2/markers.json` as it is, so a later run can apply it.
- `markers.py apply --dry-run` shows what would be written; `apply` writes
  every file in one pass, bottom up. It finds each target again by its text
  if the file changed since, goes above Python decorators, and merges into a
  marker already right above the target. Markers it cannot place stay recorded
  and are reported; fix them by hand or record them again.

Write the markers in a commit of their own.
