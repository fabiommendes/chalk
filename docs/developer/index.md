# Developer Docs

Developer docs are focused on implementation details and generated API reference.

## Contents

- API Reference: generated from source in src/chalk using mkdocstrings.

## Local workflow

```bash
uv sync --group dev
uv run mkdocs serve
```

## Writing API docs

1. Add docstrings to public modules, classes, and functions.
2. Keep argument and return descriptions concise.
3. Prefer stable examples that can run from project root.
