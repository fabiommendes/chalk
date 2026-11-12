# bootstrap-glossary

`GLOSSARY.md` at the project root holds the project vocabulary: one word per
concept, the words to avoid for it, and where it lives in the code. Humans,
agents and the code use the same words, so a word in an issue, a test name or
a class means one thing.

The glossary is not a dictionary of the project. It holds the words that
carry a meaning specific to this project, and the words people get wrong.
A good first glossary has 10 to 40 terms.

## Modes

Requires the r2 layout (`r2.toml` or `[tool.r2]`). Without it, run step 1 of
the [bootstrap](bootstrap.md) playbook first.

Pick the mode from the state of the file:

- **No `GLOSSARY.md`, or fewer than 5 terms:** build one. Go to "Build", and
  keep the terms already there.
- **A glossary with 5 terms or more:** show the count (`r2 glossary list`) and the
  result of `r2 glossary check`, then ask the human whether to update it by
  reading the project again. On yes, go to "Update"; on no, stop.

## Build

### 1. Read the documents

Read what people wrote for people, before the code. The words there are the
ones the team speaks.

- `README.md`, `AGENTS.md` or `CLAUDE.md`, `docs/`, product or design briefs
  (`PRODUCT.md`, `DESIGN.md`), `CHANGELOG.md`;
- `docs/user-stories/`, `dev/spec/`, the accepted ADRs and RFCs, the titles of
  the open issues (`r2 issue list`);
- text the user sees: UI strings, translation files, CLI help, error messages.

For each candidate word or short phrase, note where it appears, how often,
and any sentence that defines or explains it. Nouns come first (the things),
then the verbs and events that change them (`promote`, `supersede`,
`check out`) when they have a project meaning.

In a large repository, read the top-level documents in full and sample the
rest: the documents most cited, the most recent ones.

### 2. Read the code

List the main types and names the code defines: classes and records, data
models, database tables and migrations, enums and their values (statuses are
often domain words), API routes, CLI commands, event names, top-level
modules. Split compound identifiers into words (`InvoiceLineItem` → invoice,
line item).

Sort each name into one of three groups:

- **Domain.** It names something a user or the person who knows the business
  talks about, or a rule of the product. It would keep its name if the code
  were rewritten in another stack. `Invoice`, `Enrollment`, `Milestone`.
- **Generic programming.** It names a role in the code, not a thing in the
  product: `Manager`, `Handler`, `Service`, `Factory`, `Helper`, `Util`,
  `Base`, `Config`, `Settings`, `Parser`, `Cache`, `Client`, `Request`,
  `Response`, `DTO`, `Repository`, `Controller`, `Adapter`, `Wrapper`,
  `Context`, `State`, `Item`, `Data`, `Info`. These stay out of the glossary.
  Strip them from compound names and keep the rest (`InvoiceRepository` →
  `Invoice`).
- **Project technical.** A technical word with a meaning specific to this
  project that a new contributor must learn (`span` in a coverage tool, `lease`
  in a job queue). It goes in when people use it in conversation and its
  meaning here differs from the common one.

When the product is itself a developer tool, programming words can be domain
words: in a test runner, `Fixture` is domain. Decide by the first test: does
the user of the product talk about it?

Parts of a user interface follow the same test. A part the product gives its
own name, used in the docs, the help or the key bindings (the `Drawer` of an
editor, the `Inbox` of a mail client), is a term. Generic widget words
(`modal`, `button`, `tooltip`, `tab`, `sidebar` when it is just a sidebar) are
not, unless the docs use them as the name of one specific part.

### 3. Cross the two lists

| Found in | Confidence |
|---|---|
| documents and code, same word | sure |
| documents only, and the code has no name for it | sure if the documents define it; otherwise doubtful |
| documents and code, different words for what looks like the same thing | synonym conflict |
| code only | doubtful, unless the type is central (many references, in the public API) |
| one word, two different meanings in different parts of the project | meaning conflict |

Look for synonyms explicitly. Signs: two words used in the same position in
similar sentences (`ticket` in the UI, `issue` in the code); a class named one
way and its table, route or UI label another; a rename half done, with both
words in the code; documents in two languages that translate a term in more
than one way.

### 4. Choose the words to avoid

For each term, propose as words to avoid the synonyms you saw in use and the
obvious ones a newcomer would reach for. A word to avoid must not be:

- the name of another term (`r2 glossary check` fails on it);
- a word to avoid of another term, so `r2 glossary find` points one way;
- a word the public interface uses for this concept or another: a CLI command
  or option, a config key, a file name. Avoiding `runner` while the CLI has
  `--runner` makes every help page break the glossary.

The definition of a term never uses its own words to avoid.

### 5. Settle with the human

Ask in two rounds, so each fits what the human can answer at once.

**Round 1: the terms.**

1. **Sure terms**, summarized, not as a table: one line per tag with the term
   names, then only the words to avoid, as `Issue: ticket, card`. The full
   definitions go to the file, where the human reviews them in the diff. Ask
   for objections; no answer means accepted.
2. **Doubtful terms**, as checkbox questions: one option per term, with a
   short definition and where it appears, so the human ticks the ones to keep.
   Ask about the 15 most used at most; leave the rest out. A structured
   question tool usually takes a few questions of a few options each: split
   the terms by tag across questions and calls.

**Round 2: the conflicts**, after the answers of round 1. One question per
conflict, numbered `C1`, `C2`... so the human can answer in text when the tool
does not fit.

- **Synonym conflict:** which word wins (one option per word, with where
  each is used), and what to do with the code:
  - rename in the code now;
  - open an issue for the rename (`r2 issue new ... --kind task`);
  - keep the code as it is: the glossary records the code name in `code`,
    and the losing word goes to `avoid` for prose only.

  If the two words turn out to be two different concepts, both become terms
  and each definition says how it differs from the other.
- **Meaning conflict:** rename one of the uses, or keep both as separate
  terms qualified by where they apply, `## Account (Billing)` and
  `## Account (Auth)`.

When an answer brings a new word (a third name for a conflict), run
`r2 glossary find` on it and check it against the code and the docs before
taking it: the new word must not clash with another term either.

For each conflict whose rename touches a **published contract** (a file
format others write, a public API, CLI commands or options, config keys, a
spec other repositories follow), say so in the question and offer, instead of
a plain rename: read both names and write the new one, updating the spec,
the docs and any copy of them (an installed skill, a template); or an issue
for later.

Record what the human turned down or put off, so the next update does not
propose it again (see "Excluded words").

### 6. Write

If `GLOSSARY.md` does not exist, create it with this skeleton (`r2 glossary`
refuses to write a file without `type: glossary`):

```markdown
---
type: glossary
status: active
---

# Glossary

One or two sentences on what the project is and who uses these words.

---
```

Then add all the accepted terms in one call, in the format of the file, with
a quoted heredoc delimiter so the shell leaves the text alone:

```sh
r2 glossary add - <<'EOF'
## Invoice

A request for payment sent to a customer for the orders of one billing period.

- tags: billing
- avoid: bill, charge
- related: Order, Customer
- code: billing.models.Invoice
- pt: fatura

## Order

What a customer buys in one checkout.
EOF
```

It is all or nothing: a term that already exists, a name repeated in the
input or a malformed field makes it exit 1, list the problems and write
nothing. Fix the input and run it again. The field options (`--tag`,
`--avoid`...) do not mix with `-`; the fields go in the input.

- The term name is in the language of the code, singular, capitalized as a
  title.
- A language field (`pt: fatura`) records a translation that the
  documents in that language already use, or one the human gives. Do not
  translate terms on your own; a term without a translation in use gets none.
- The definition says what the thing is in the product, in one or two
  sentences, with the words of the documents. It does not say how it is built.
  It can use other terms; list them in `related`.
- `code` points to the class, type or function that is the concept, fully
  qualified (`billing.models.Invoice`). Add a second one only when the concept
  has another representation people work with (the model and its wire type).
  Point to a module only when no single name stands for the concept. When
  unsure which of several types is the concept, leave `code` out and say so.
- `tags` groups terms when the glossary is large (by area of the product).

Run `r2 glossary check` and fix what it reports, then `r2 glossary fmt`.

### 7. Apply the decisions

For each conflict where the human chose to rename the code now: rename, run
`r2 check` (or the tests), and commit the rename on its own, apart from the glossary. For each
"open an issue": create it with the old word, the new word and the places to
change, and `--relatedTo GLOSSARY.md`.

Commit the glossary apart from the renames.

Finish with a short summary: terms added, conflicts settled, issues opened,
renames done.

## Excluded words

Candidates the human rejected or put off go in the frontmatter of
`GLOSSARY.md`, which r2 keeps as written:

```yaml
---
type: glossary
status: active
rejected: [Pane (herdr), Session]
deferred: [Brief, Persona]
---
```

- `rejected`: not terms of this project. Never propose them again.
- `deferred`: maybe later, usually because that part of the project is still
  changing. Propose them again only when the human asks, or when the part they
  belong to has settled (its RFC accepted, its spec active).

Edit these two lists by hand; `r2 glossary` has no option for them.

## Update

1. `r2 glossary check`; fix what it reports first.
2. `r2 glossary list --json` to load the current terms, and read `rejected`
   and `deferred` in the frontmatter.
3. Run steps 1 to 3 of "Build", and keep only what changed:
   - new candidate terms not in the glossary;
   - terms whose `code` points to names or paths that no longer exist;
   - words listed under `avoid` that appear in the code, the UI or the
     documents written after the term was added (search for each);
   - terms that appear nowhere any more: propose removing them;
   - new synonym and meaning conflicts;
   - nothing from `rejected`, and from `deferred` only as the section above
     says.
4. Settle with the human as in step 5 of "Build", and write with
   `r2 glossary add -` for the new terms, `set TERM` (each field option replaces the whole field;
   `--unset KEY` removes one) and `remove TERM`.
5. `r2 glossary check`, `r2 glossary fmt`, apply the decisions, summarize.
