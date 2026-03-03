# arxiv-coffe Implementation Plan

## Architecture Overview

```
arxiv-coffe/
├── pyproject.toml              # dependencies & entry point
├── main.py                     # entry point: launch TUI
├── config.toml.example         # example config
├── interests.md.example        # example interests file
├── src/
│   └── arxiv_coffe/
│       ├── __init__.py
│       ├── app.py              # Textual App (main TUI)
│       ├── config.py           # Config loading/saving (TOML)
│       ├── arxiv_client.py     # arXiv paper fetching
│       ├── pdf_extractor.py    # PDF download + text extraction (pymupdf)
│       ├── llm.py              # LLM integration via litellm
│       ├── library.py          # library.md management
│       ├── models.py           # Data classes (Paper, Summary, etc.)
│       └── screens/
│           ├── __init__.py
│           ├── feed.py         # Paper feed screen (browse + AI filter)
│           ├── summary.py      # Summary viewer screen
│           ├── settings.py     # Settings/config editor screen
│           └── library.py      # Library browser screen
└── output/                     # default output folder (user-configurable)
    ├── library.md              # central index
    └── hep-ph/
        └── 2026-03-03_paper-title.md
```

## Stack

| Component        | Package                                        |
| ---------------- | ---------------------------------------------- |
| arXiv data       | `arxiv`                                        |
| TUI              | `textual`                                      |
| PDF extraction   | `pymupdf`                                      |
| LLM              | `litellm`                                      |
| Config (read)    | `tomllib` (stdlib, Python 3.11+)               |
| Config (write)   | `tomli-w`                                      |

---

## Phase 1: Foundation (config, models, project setup)

### 1.1 Project setup
- Update `pyproject.toml`: add dependencies (`textual`, `arxiv`, `pymupdf`, `litellm`, `tomli-w`), entry point (`arxiv-coffe = "main:main"`), package structure
- Create `src/arxiv_coffe/` package structure with all subdirectories

### 1.2 Data models (`models.py`)
- `Paper` dataclass: `arxiv_id`, `title`, `authors: list[str]`, `abstract`, `categories: list[str]`, `published: datetime`, `pdf_url`, `relevance_score: float | None`, `relevance_reason: str | None`
- `SummaryResult` dataclass: `paper: Paper`, `summary_text: str`, `generated_at: datetime`, `model_used: str`, `output_path: Path`
- `AppConfig` dataclass: `api_key`, `model` (litellm model string), `interests_file: Path`, `output_dir: Path`, `categories: list[str]`, `max_papers: int`, `date_range_days: int`

### 1.3 Configuration (`config.py`)
- Default config path: `~/.config/arxiv-coffe/config.toml`
- Load/save config as TOML using `tomllib` (read) and `tomli-w` (write)
- Fields:
  - `llm.api_key` — API key for litellm
  - `llm.model` — e.g. `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4-20250514"`
  - `llm.base_url` — optional custom endpoint
  - `arxiv.categories` — list of arxiv categories (e.g. `["hep-ph", "hep-th"]`)
  - `arxiv.max_papers` — max papers to fetch per category
  - `paths.interests_file` — path to user interests markdown file
  - `paths.output_dir` — path to output folder
- Ship `config.toml.example` with documented fields

---

## Phase 2: Core services (arxiv, PDF, LLM)

### 2.1 arXiv client (`arxiv_client.py`)
- `fetchLatestPapers(categories, max_results) -> list[Paper]`
  - Queries arxiv sorted by `SubmittedDate`
  - Maps `arxiv.Result` objects to `Paper` dataclass
- `fetchPapersByDateRange(categories, start, end, max_results) -> list[Paper]`
  - Same but filtered by user-specified date range
- Respect rate limiting (3s between requests per arxiv ToS)

### 2.2 PDF extractor (`pdf_extractor.py`)
- `downloadPdf(paper: Paper, tmp_dir: Path) -> Path`
  - Downloads PDF using the `arxiv` library's `download_pdf()` method
- `extractText(pdf_path: Path) -> str`
  - Uses `pymupdf` (fitz) to extract full text from all pages
- Cleanup temp files after extraction

### 2.3 LLM integration (`llm.py`)
- `filterPapersByRelevance(papers: list[Paper], interests: str, config) -> list[Paper]`
  - Sends paper titles + abstracts in batches to the LLM alongside the user's interests description
  - Returns papers sorted by relevance, with `relevance_score` (0-10) and `relevance_reason` populated
  - Uses structured output (JSON) for reliable parsing
- `summarizePaper(paper: Paper, full_text: str, config) -> str`
  - Sends full paper text to LLM with a system prompt requesting a concise but exhaustive summary
  - Returns markdown-formatted summary text
- Both functions use `litellm.acompletion()` (async) with the user-configured model string and API key
- System prompts stored as module-level constants for consistency and easy tuning

---

## Phase 3: Library management

### 3.1 Library manager (`library.py`)
- `writeSummaryFile(result: SummaryResult, output_dir: Path) -> Path`
  - Writes a markdown file at `{output_dir}/{category}/{date}_{short-title}.md`
  - File format:
    ```markdown
    # {title}
    **Authors:** ...
    **arXiv:** {link}  |  **Published:** {date}  |  **Categories:** ...

    ## Abstract
    {abstract}

    ## Summary
    {AI-generated summary}

    ---
    *Summarized by {model} on {date}*
    ```
- `updateLibraryIndex(output_dir: Path)`
  - Rebuilds `library.md` by scanning all summary files in the output directory
  - Format:
    ```markdown
    # arxiv-coffe Library

    ## hep-ph
    | Date | Title | arXiv | Summary |
    |------|-------|-------|---------|
    | 2026-03-03 | Paper Title | [2603.01234](link) | [summary](relative-link) |

    ## hep-th
    ...

    ---
    *Last updated: {timestamp}*
    ```
- `addToLibrary(result: SummaryResult, output_dir: Path)`
  - Writes summary file + appends entry to library.md (without full rebuild)

---

## Phase 4: TUI Screens

### 4.1 Main App (`app.py`)
- Textual `App` subclass with header, footer, and screen switching
- Screens: Feed, Library, Settings
- Keybindings: `f` = feed, `l` = library, `s` = settings, `q` = quit

### 4.2 Feed Screen (`screens/feed.py`) — the main workflow screen
- **Top bar:** category selector (dropdown/tabs), date range picker (or "latest" toggle), "Fetch" button
- **On fetch:** show loading spinner, call `fetchLatestPapers()` or `fetchPapersByDateRange()`, display results in a `DataTable` (title, authors, date, categories)
- **"AI Filter" button:** calls `filterPapersByRelevance()`, re-sorts table by relevance, adds a relevance column with score + short reason
- **Selection:** each row has a checkbox; user selects papers to summarize
- **"Summarize Selected" button:** for each selected paper:
  1. Show progress bar
  2. Download PDF
  3. Extract text
  4. Call `summarizePaper()`
  5. Write output file
  6. Update library index
- **Detail panel:** clicking a row opens a side/bottom panel showing abstract and full metadata

### 4.3 Summary Viewer Screen (`screens/summary.py`)
- Renders a summary markdown file using Textual's built-in `Markdown` widget
- Navigation back to feed or library

### 4.4 Library Screen (`screens/library.py`)
- Lists all previously summarized papers from the output directory
- Searchable/filterable `DataTable` (by title, category, date)
- Click to open summary in Summary Viewer

### 4.5 Settings Screen (`screens/settings.py`)
- Form with `Input` widgets for: API key, model string, interests file path, output directory, categories (comma-separated), max papers
- "Save" button writes to `config.toml`
- "Edit Interests" opens the interests file in the system editor or inline `TextArea`

---

## Phase 5: Polish & UX

- **Error handling:** network failures, API errors, invalid config — show user-friendly error notifications via Textual's notification system
- **Async:** all network/LLM calls are async so the TUI stays responsive (workers / `run_worker`)
- **Progress indicators:** spinners during fetch, progress bar during batch summarization with per-paper status
- **First-run experience:** if no config exists, redirect to Settings screen with sensible defaults pre-filled
- **Interests file example:** ship `interests.md.example` showing expected format
- **Keyboard shortcuts:** consistent navigation, vim-style where appropriate

---

## Implementation Order

| Step | What                                    | Files                                        |
| ---- | --------------------------------------- | -------------------------------------------- |
| 1    | Project setup, deps, package structure  | `pyproject.toml`, directory creation          |
| 2    | Config + models                         | `config.py`, `models.py`, `config.toml.example` |
| 3    | arXiv client                            | `arxiv_client.py`                            |
| 4    | PDF extractor                           | `pdf_extractor.py`                           |
| 5    | LLM integration                        | `llm.py`                                     |
| 6    | Library manager                         | `library.py`                                 |
| 7    | TUI app shell + settings screen         | `app.py`, `screens/settings.py`              |
| 8    | Feed screen (fetch + display)           | `screens/feed.py`                            |
| 9    | Feed screen (AI filter + summarize)     | `screens/feed.py`                            |
| 10   | Library + summary viewer screens        | `screens/library.py`, `screens/summary.py`   |
| 11   | Polish, error handling, first-run       | All                                          |
| 12   | Example files, README                   | `interests.md.example`, `README.md`          |

---

## Design Decisions

- **litellm** for LLM: supports 100+ providers via a single `completion()` call. User sets model as e.g. `"openai/gpt-4o"` or `"anthropic/claude-sonnet-4-20250514"` in config.
- **pymupdf** for PDF extraction: fastest and most accurate option for academic papers.
- **TOML config** at `~/.config/arxiv-coffe/config.toml`: clean, human-editable, editable from within the TUI.
- **Paper feed:** defaults to latest submissions, with optional date range picker for historical search.
- **Library index:** `library.md` serves as a human-readable, git-friendly central catalog of all summarized papers.
