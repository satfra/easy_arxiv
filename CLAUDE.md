# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

arxiv-coffee is a dual-mode app (Textual TUI + Unix-pipe CLI) for fetching arXiv papers, filtering them by relevance using an LLM, summarizing PDFs, and managing a local library of summaries. Both modes share the same business logic; UI layers are purely presentation.

## Development Commands

```bash
uv sync                              # install dependencies
uv sync --extra graphics             # also install textual-image for inline math images
uv run main.py                       # launch TUI (default when no subcommand)
uv run main.py tui                   # explicit TUI launch
```

CLI pipeline (Unix pipes):
```bash
uv run main.py feed                  # fetch papers → stdout JSONL
uv run main.py feed | uv run main.py rate
uv run main.py feed | uv run main.py rate | uv run main.py summarize
uv run main.py feed | uv run main.py rate | uv run main.py summarize | uv run main.py export --digest --open
```

Linter: `ruff` (dev dependency). No test suite exists.

Build backend: `hatchling`. Source package: `src/arxiv_coffee`. Python >=3.12.

## Architecture

### Data Flow

Papers flow through a 4-stage pipeline as JSONL (`Paper` dataclass serialized via `toDict`/`fromDict` in `models.py`):

1. **Feed** (`arxiv_client.py`): Fetches from arXiv API. Computes announcement windows using US/Eastern 20:00 cutoff. Builds `cat:X OR cat:Y` queries.
2. **Rate** (`llm.py:filterPapersByRelevance`): Batches papers (size 5), fires all batches concurrently via `asyncio.gather`, each hits `litellm.acompletion`. Populates `relevance_score`/`relevance_reason`.
3. **Summarize** (`summarize_pipeline.py` → `pdf_extractor.py` → `llm.py:summarizePaper`): Downloads PDF via httpx, extracts text with pymupdf in a thread, calls LLM (truncates at 80k chars), writes markdown to library. Progress via `PipelineProgress` callback dataclass.
4. **Export** (`html_export.py`): Markdown → HTML using `markdown-it-py` with `dollarmath_plugin`. Math rendered as MathJax delimiters. `--digest` mode builds combined TOC document.

### TUI vs CLI separation

- **CLI**: `cli.py` defines a Typer app with `feed`/`rate`/`summarize`/`export` subcommands. Each reads JSONL from stdin, processes, writes JSONL to stdout.
- **TUI**: `app.py` (Textual App) with screens in `screens/`. FeedScreen uses `@work(thread=False)` async workers mirroring the CLI stages but updating widgets inline.

### Key modules

- `models.py`: `Paper` and `AppConfig` dataclasses — the universal data types passed everywhere.
- `llm.py`: LLM calls + `_RateLimiter` (async token-bucket semaphore combining concurrency cap and sliding-window RPM).
- `config.py`: Reads/writes `~/.config/arxiv-coffee/config.toml` (via `tomllib`/`tomli-w`) and `interests.md`.
- `library.py`: On-disk structure is `{output_dir}/{primary_category}/{YYYY-MM-DD}_{slug}.md`. Manages `library.md` index.
- `copilot_auth.py`: GitHub Copilot OAuth device flow. Cached token at `~/.config/litellm/github_copilot/access-token`. `checkLlmAuth` gates all LLM operations.
- `widgets/math_markdown.py`: Subclasses Textual Markdown, handles LaTeX→Unicode (inline) and LaTeX→PIL image (display math blocks).
- `widgets/dual_progress.py`: Custom 3-segment progress bar (downloading/summarizing/done).

### Conventions

- Business logic lives in top-level `src/arxiv_coffee/*.py` modules; screens in `screens/` are presentation only.
- All async LLM calls go through `litellm.acompletion` — the project uses litellm as a unified LLM abstraction.
- JSONL is the interchange format between pipeline stages (stdin/stdout).
- `camelCase` function names throughout (e.g., `fetchLatestPapers`, `filterPapersByRelevance`).
