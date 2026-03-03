# arxiv-coffeee

The scientific method: 1. Coffee. 2. Open arXiv. 3. Existential dread.
This tool automates step 2, giving you more time for step 1 (and hopefully less of step 3).

**arxiv-coffeee** is a terminal UI application that fetches new papers from arXiv, uses AI to filter them by relevance to your research, and generates structured summaries of the ones you care about.

## Features

- **Browse arXiv** — fetch latest submissions or papers from a custom date range, across multiple physics categories (hep-ph, hep-th, astro-ph, etc.)
- **AI relevance filtering** — send paper titles and abstracts to an LLM alongside your research interests; papers get scored 0-10 and sorted
- **PDF summarization** — download full PDFs, extract text, and generate concise but exhaustive markdown summaries via AI
- **Library management** — summaries are written to organized markdown files with a central `library.md` index
- **Multi-provider LLM support** — uses [litellm](https://github.com/BerriAI/litellm) so you can plug in OpenAI, Anthropic, local models, or any provider litellm supports

## Installation

Requires Python 3.12+.

```bash
# Clone the repository
git clone <repo-url>
cd easy_arxiv

# Run (handles virtualenv + dependency installation automatically)
./arxiv-coffeee
```

The `arxiv-coffeee` launcher script will:
1. Detect whether `uv` or `pip` is available
2. Create a virtualenv and install all dependencies if needed
3. Launch the TUI

You can also manage the environment manually:

```bash
# With uv
uv sync && uv run arxiv-coffeee

# With pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e . && python main.py
```

## Configuration

On first launch, arxiv-coffeee creates a config file at `~/.config/arxiv-coffee/config.toml` and opens the Settings screen automatically.

You can also copy the example config:

```bash
mkdir -p ~/.config/arxiv-coffee
cp config.toml.example ~/.config/arxiv-coffee/config.toml
```

### Required settings

| Setting | Description | Example |
|---------|-------------|---------|
| `llm.api_key` | API key for your LLM provider | `sk-...` |
| `llm.model` | Model in litellm format | `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`, `github_copilot/gpt-4o` |

### Optional settings

| Setting | Default | Description |
|---------|---------|-------------|
| `llm.base_url` | *(empty)* | Custom API endpoint (e.g., for local models) |
| `arxiv.categories` | `["hep-ph"]` | arXiv categories to fetch |
| `arxiv.max_papers` | `50` | Max papers per fetch |
| `paths.interests_file` | `~/.config/arxiv-coffee/interests.md` | Your research interests (used by AI filter) |
| `paths.output_dir` | `~/arxiv-coffee-library` | Where summaries are saved |

### Interests file

Create a markdown file describing your research interests. The AI uses this to score papers by relevance. See `interests.md.example` for the expected format.

### Using GitHub Copilot as the LLM provider

If you have a [GitHub Copilot](https://github.com/features/copilot) subscription, you can use it as your LLM provider with no separate API key required. litellm handles authentication automatically via GitHub's OAuth device flow.

1. Set the model to a `github_copilot/` prefixed model name in your config:

```toml
[llm]
api_key = ""
model = "github_copilot/gpt-4o"
```

2. On first run, litellm will print a device code and a URL in the terminal. Open the URL, enter the code, and authorize the app with your GitHub account.

3. Credentials are cached locally — subsequent runs authenticate automatically.

Available models depend on your Copilot plan. Common options:

| Model string | Description |
|---|---|
| `github_copilot/gpt-4o` | GPT-4o via Copilot |
| `github_copilot/gpt-4o-mini` | GPT-4o Mini via Copilot |
| `github_copilot/claude-sonnet-4-20250514` | Claude Sonnet via Copilot |
| `github_copilot/o3-mini` | o3-mini via Copilot |

You can also use **GitHub Models** (a separate service at [github.com/marketplace/models](https://github.com/marketplace/models)) with the `github/` prefix. This requires a GitHub personal access token set as `api_key` or via the `GITHUB_API_KEY` environment variable:

```toml
[llm]
api_key = "ghp_..."
model = "github/gpt-4o"
```

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
~/arxiv-coffee-library/
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
