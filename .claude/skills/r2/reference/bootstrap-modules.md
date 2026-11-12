# bootstrap-modules

Give each package of the project a description, so the module map
(`r2 modules`, also the first section of `r2 context`) tells an agent what
each part of the code is for before it reads the code. The description is the
first paragraph of the first comment block at the top of the file: it lives in
the code and is reviewed with it.

| Language | File of a package | Description |
|---|---|---|
| Python | `__init__.py` | the module docstring, or a `#` comment above it |
| Rust | `lib.rs`, `main.rs`, `mod.rs`, or `name.rs` next to the folder `name/` | `//!` doc comments, or `//` comments |

A docstring (`//!` in Rust) goes into the generated documentation; a comment
stays in the code. So the choice is a decision about the public API: a module
with a docstring is documented and becomes part of the public interface. Write
a docstring for what is clearly public (exported, imported by users of the
project, listed in the docs) and a header comment for what is clearly internal.

The module map reads only these languages. In a project with none of them,
say so and stop.

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first. Use the terms of `GLOSSARY.md`
in the descriptions; when there is no glossary, suggest running
`bootstrap-glossary` first.

Rules:

- **Describe what the code does, not what it should do.** Every description
  comes from reading the package. Never invent a purpose or a rule.
- **Propose, then write.** Change no file the human did not keep.
- **Additive and safe to run again.** Never rewrite an existing description;
  only fill the missing ones.
- **Do not commit** unless the human asks.

## 1. Find what has no description

```sh
r2 modules --missing
```

It lists the packages and the source files without a description, outside
the tests. Leave out folders that are not code (`docs/`,
`assets/`) and generated or vendored code. Start with the packages; propose a
file only when it is a module others import (a public API, an entry point),
not a script or a one-off.

## 2. Draft

For each package, read its files: the public names, the descriptions its
files already have, who imports it. Draft the first paragraph:

- The first sentence says what the package or file is for in the product,
  in one line: `Per-test coverage: record which code each test runs and analyse the
  suite.` It is what the module map shows.
- A second sentence only when the code shows a rule that holds for the whole
  package: `Pure functions: no I/O.`, `Only the CLI imports this package.`
  Note each such rule: it is an ADR candidate for `bootstrap-adrs`.
- When the purpose is not clear from the code, say so instead of drafting.

## 3. Settle with the human

Show the drafts as a checkbox question: one line each with the path, the
form (docstring or comment) and the first sentence. Ask in a separate question
only about the modules whose form you are unsure of: public interface or not. Ask about the unclear packages in the same message. The
human ticks the ones to keep and may correct the text.

## 4. Write

Write each kept description with the editor, at the top of the package file,
creating the file when the package has none (a Python namespace package gets
an `__init__.py` only when the human agrees, since it changes how the package
imports). Keep the language the human chose for code comments.

Run `r2 modules --missing` again and check that each written package and
file left the list. Run `r2 check` when it exists, or the project's linters.

## 5. Finish

1. Summarize in a few lines: packages described, packages left without a
   description and why, rules noted as ADR candidates.
2. Propose one commit with the descriptions, and wait for the human. When this
   runs as a phase of `bootstrap`, pass the noted rules on to
   `bootstrap-adrs`.
