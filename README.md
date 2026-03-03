# arxiv-coffe

The scientific method: 1. Coffee. 2. Open arXiv. 3. Existential dread.
This tool automates step 2, giving you more time for step 1 (and hopefully less of step 3).

**arxiv-coffe** is a terminal UI application that fetches new papers from arXiv, uses AI to filter them by relevance to your research, and generates structured summaries of the ones you care about.

## Features

- **Browse arXiv** — fetch latest submissions or papers from a custom date range, across multiple physics categories (hep-ph, hep-th, astro-ph, etc.)
- **AI relevance filtering** — send paper titles and abstracts to an LLM alongside your research interests; papers get scored 0-10 and sorted
- **PDF summarization** — download full PDFs, extract text, and generate concise but exhaustive markdown summaries via AI
- **Library management** — summaries are written to organized markdown files with a central `library.md` index
- **Multi-provider LLM support** — uses [litellm](https://github.com/BerriAI/litellm) so you can plug in OpenAI, Anthropic, local models, or any provider litellm supports

## Installation

Requires Python 3.12+. Uses [uv](https://github.com/astral-sh/uv) for package management.

```bash
# Clone the repository
git clone <repo-url>
cd easy_arxiv

# Install dependencies
uv sync

# Run
uv run arxiv-coffe
# or
uv run python main.py
```

## Configuration

On first launch, arxiv-coffe creates a config file at `~/.config/arxiv-coffe/config.toml` and opens the Settings screen automatically.

You can also copy the example config:

```bash
mkdir -p ~/.config/arxiv-coffe
cp config.toml.example ~/.config/arxiv-coffe/config.toml
```

### Required settings

| Setting | Description | Example |
|---------|-------------|---------|
| `llm.api_key` | API key for your LLM provider | `sk-...` |
| `llm.model` | Model in litellm format | `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514` |

### Optional settings

| Setting | Default | Description |
|---------|---------|-------------|
| `llm.base_url` | *(empty)* | Custom API endpoint (e.g., for local models) |
| `arxiv.categories` | `["hep-ph"]` | arXiv categories to fetch |
| `arxiv.max_papers` | `50` | Max papers per fetch |
| `paths.interests_file` | `~/.config/arxiv-coffe/interests.md` | Your research interests (used by AI filter) |
| `paths.output_dir` | `~/arxiv-coffe-library` | Where summaries are saved |

### Interests file

Create a markdown file describing your research interests. The AI uses this to score papers by relevance. See `interests.md.example` for the expected format.

## Usage

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `f` | Open Feed screen / Fetch papers |
| `l` | Open Library screen |
| `s` | Open Settings screen |
| `q` | Quit |

### Feed screen

| Key | Action |
|-----|--------|
| `f` | Fetch papers from arXiv |
| `a` | Run AI relevance filtering |
| `Space` | Toggle paper selection |
| `Ctrl+A` | Select/deselect all |
| `s` | Summarize selected papers |
| `d` | Toggle detail panel |
| `Escape` | Go back |

### Workflow

1. **Configure** — set your API key, model, and research interests in Settings
2. **Fetch** — pick a category and fetch papers (latest or by date range)
3. **Filter** — press `a` to run AI filtering; papers are scored and sorted by relevance
4. **Select** — use `Space` to pick papers you want summarized
5. **Summarize** — press `s`; each paper's PDF is downloaded, text extracted, and summarized by the AI
6. **Browse** — summaries appear in the Library screen and as markdown files in your output directory

### Output structure

```
~/arxiv-coffe-library/
├── library.md              # Central index of all summaries
├── hep-ph/
│   ├── 2026-03-03_susy-at-the-lhc.md
│   └── 2026-03-03_dark-matter-searches.md
└── hep-th/
    └── 2026-03-02_string-landscape.md
```

## Dependencies

- [textual](https://github.com/Textualize/textual) — terminal UI framework
- [arxiv](https://github.com/lukasschwab/arxiv.py) — arXiv API client
- [pymupdf](https://github.com/pymupdf/PyMuPDF) — PDF text extraction
- [litellm](https://github.com/BerriAI/litellm) — unified LLM API
- [httpx](https://github.com/encode/httpx) — async HTTP client (for PDF downloads)
- [tomli-w](https://github.com/hukkin/tomli-w) — TOML writing

## License

MIT
