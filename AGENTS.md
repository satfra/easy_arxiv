# AGENTS.md — arxiv-coffee

## Project Overview

arxiv-coffee is a Python TUI (Textual) application that fetches arXiv papers,
filters them by relevance using LLMs (via litellm), and generates structured
markdown summaries. Source layout: `src/arxiv_coffee/`.

## Build & Run

```bash
# Install dependencies (uv is the primary package manager)
uv sync

# Run the TUI
uv run arxiv-coffee        # via entry point
uv run python main.py      # alternative

# Install in editable mode (pip fallback)
pip install -e .
```

Build backend is Hatchling. Entry point: `arxiv_coffee.app:run`.

## Tests

**No test suite exists yet.** There are no tests, no pytest config, and no test
dependencies. If adding tests:

- Use `pytest` as the test framework
- Place tests in `tests/` at the repo root
- Name test files `test_*.py`
- Run a single test: `uv run pytest tests/test_foo.py::test_function_name -v`
- Run all tests: `uv run pytest`

## Linting & Formatting

Ruff is used with default settings (no explicit config in pyproject.toml).

```bash
uv run ruff check .          # lint
uv run ruff check --fix .    # lint + autofix
uv run ruff format .         # format
```

No mypy, black, isort, or flake8 configuration exists.

## Code Style

### Language & General

- Python 3.12+ (`.python-version` pins 3.14, `requires-python = ">=3.12"`)
- Every module starts with `from __future__ import annotations` on line 1
- Use f-strings for all string formatting (except `%`-style in `logging` calls)
- 2-space indentation is NOT used here — this project uses **4-space indentation** (Python standard)
- Keep code concise; no unnecessary abstractions

### Naming Conventions

| Element             | Convention        | Examples                                        |
|---------------------|-------------------|-------------------------------------------------|
| Functions/methods   | **camelCase**     | `loadConfig`, `fetchLatestPapers`, `_slugify`   |
| Variables/params    | **snake_case**    | `max_papers`, `scored`, `authors_str`           |
| Classes             | **PascalCase**    | `Paper`, `FeedScreen`, `ArxivCoffeApp`          |
| Constants           | **UPPER_SNAKE**   | `FILTER_SYSTEM_PROMPT`, `CATEGORY_OPTIONS`      |
| Private functions   | **_camelCase**    | `_resultToPaper`, `_buildCategoryQuery`         |

**Important:** Functions use camelCase, NOT snake_case. This is a deliberate
project convention. Function names should start with verbs
(e.g., `getUserById`, `fetchLatestPapers`, `writeSummaryFile`).

### Imports

Strict 3-group ordering separated by blank lines:

```python
from __future__ import annotations          # always first

import asyncio                               # 1. stdlib
from pathlib import Path

import httpx                                 # 2. third-party

from arxiv_coffee.models import Paper        # 3. local (absolute only)
```

- **Absolute imports only** — use `from arxiv_coffee.X import Y`, never relative
- Prefer `from X import Y` over bare `import X` (except for top-level packages
  like `import arxiv`, `import litellm`, `import fitz`, `import httpx`)
- No imports from `typing` — use built-in generics (`list[str]`, `dict[str, X]`)
  and PEP 604 unions (`X | Y`) enabled by `__future__.annotations`

### Type Annotations

- **100% coverage** on all function signatures (parameters + return types)
- Use built-in generics: `list[str]`, `dict[str, tuple[float, str]]`, `set[str]`
- Use PEP 604 unions: `Path | None`, `float | None` (never `Optional[X]`)
- Use `*` separator for keyword-only arguments: `def foo(x: int, *, bar: int = 5)`
- Annotate instance variables in `__init__`: `self.papers: list[Paper] = []`

### Docstrings

- Plain prose style (not Sphinx/Google/NumPy format)
- Present on all public functions/classes and most private helpers
- Single-line for simple functions: `"""Convert an arxiv.Result to our Paper dataclass."""`
- Multi-line: summary line, blank line, elaboration

### Error Handling

- Use specific exception types for recoverable errors (`except OSError`, `except ValueError`)
- Broad `except Exception` only at UI boundaries (Textual event handlers/workers)
- Raise `ValueError` for precondition failures (e.g., missing API key)
- No custom exception classes — use built-in types only
- Use `response.raise_for_status()` for HTTP error propagation
- `try/finally` for resource cleanup (temp files, downloads)

### Async Patterns

- `async def` for all I/O-bound operations (network, LLM, PDF download)
- `asyncio.to_thread()` to wrap blocking calls (arxiv API, PDF parsing)
- Textual `@work(thread=False)` decorator for background TUI tasks
- Use native async libraries directly (`httpx.AsyncClient`, `litellm.acompletion`)

### Data Classes & Logging

- Plain `@dataclass` (no `frozen`, `slots`, or `__post_init__`)
- `field(default_factory=...)` for mutable defaults; `@property` for computed attributes
- `logging.getLogger(__name__)` in non-UI modules (currently only `llm.py`)
- `%`-style formatting in `logger.warning(...)` calls (deferred interpolation)
- In Textual screens: use `self.notify(msg, severity="error")` for user feedback
  and `self.log.warning(...)` for debug logging

### Module Structure

Every source file follows this layout:

1. `from __future__ import annotations`
2. Stdlib imports
3. Third-party imports
4. Local imports
5. Module-level constants (prompts, config paths, option lists)
6. Functions and classes
7. Section dividers (`# ---...`) to separate Actions / Event handlers / Workers / Helpers in screen files

### Textual UI Conventions

- Screen classes inherit from `Screen` and define `BINDINGS` and `CSS` as class attributes
- `compose()` yields the widget tree using `ComposeResult`
- Screens accept config/data in `__init__` and call `super().__init__()`
- Action methods: `action_openFeed`, `action_fetchPapers`
- Event handlers: `onFetch`, `onRowSelected`, `handleSave`

## Project Structure

Source code lives in `src/arxiv_coffee/`. Key modules: `app.py` (Textual App,
entry point), `arxiv_client.py` (arXiv API), `config.py` (TOML config),
`llm.py` (LLM via litellm), `models.py` (dataclasses), `pdf_extractor.py`
(PDF download + text extraction), `library.py` (summary writing + index).
Screens are in `screens/`: `feed.py`, `library_screen.py`, `settings.py`,
`summary.py`. Entry point: `main.py` -> `arxiv_coffee.app:run`.
