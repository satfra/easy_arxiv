# arxiv-coffee

The scientific method: 1. Coffee. 2. Open arXiv. 3. Existential dread.
This tool automates step 2, giving you more time for step 1 (and hopefully less of step 3).

**arxiv-coffee** is both a terminal UI application and a composable CLI pipeline. It fetches new papers from arXiv, uses AI to filter them by relevance to your research, and generates structured summaries of the ones you care about.

## Features

- **Browse arXiv** — fetch latest submissions or papers from a custom date range, across multiple physics categories (hep-ph, hep-th, astro-ph, etc.)
- **AI relevance filtering** — send paper titles and abstracts to an LLM alongside your research interests; papers get scored 0-10 and sorted
- **PDF summarization** — download full PDFs, extract text, and generate concise but exhaustive markdown summaries via AI
- **Library management** — summaries are written to organized markdown files with a central `library.md` index
- **HTML export** — convert summaries to self-contained HTML with pre-rendered LaTeX math, suitable for browser viewing or emailing
- **Multi-provider LLM support** — uses [litellm](https://github.com/BerriAI/litellm) so you can plug in OpenAI, Anthropic, local models, or any provider litellm supports
- **Unix-pipe CLI** — compose the pipeline stages freely on the command line

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone the repository
git clone <repo-url>
cd arxiv_coffe

# Install dependencies and launch the TUI
uv sync
uv run main.py
```

## Configuration

On first launch, `uv run main.py` creates a config file at `~/.config/arxiv-coffee/config.toml` and opens the Settings screen automatically.

You can also copy the example config:

```bash
mkdir -p ~/.config/arxiv-coffee
cp config.toml.example ~/.config/arxiv-coffee/config.toml
```

### Required settings

| Setting       | Description                   | Example                                                                        |
| ------------- | ----------------------------- | ------------------------------------------------------------------------------ |
| `llm.api_key` | API key for your LLM provider | `sk-...`                                                                       |
| `llm.model`   | Model in litellm format       | `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`, `github_copilot/gpt-4o` |

### Optional settings

| Setting                     | Default                               | Description                                       |
| --------------------------- | ------------------------------------- | ------------------------------------------------- |
| `llm.base_url`              | *(empty)*                             | Custom API endpoint (e.g., for local models)      |
| `arxiv.categories`          | `["hep-ph"]`                          | arXiv categories to fetch                         |
| `arxiv.max_papers`          | `100`                                 | Max papers per fetch                              |
| `arxiv.include_cross_posts` | `false`                               | Include papers cross-posted from other categories |
| `paths.interests_file`      | `~/.config/arxiv-coffee/interests.md` | Your research interests (used by AI filter)       |
| `paths.output_dir`          | `~/arxiv-coffee-library`              | Where summaries are saved                         |

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

2. On first run, `uv run main.py` will print a device code and a URL in the terminal. Open the URL, enter the code, and authorize the app with your GitHub account.

3. Credentials are cached locally — subsequent runs authenticate automatically.

Available models depend on your Copilot plan. Common options:

| Model string                              | Description               |
| ----------------------------------------- | ------------------------- |
| `github_copilot/gpt-4o`                   | GPT-4o via Copilot        |
| `github_copilot/gpt-4o-mini`              | GPT-4o Mini via Copilot   |
| `github_copilot/claude-sonnet-4-20250514` | Claude Sonnet via Copilot |
| `github_copilot/o3-mini`                  | o3-mini via Copilot       |

You can also use **GitHub Models** (a separate service at [github.com/marketplace/models](https://github.com/marketplace/models)) with the `github/` prefix. This requires a GitHub personal access token set as `api_key` or via the `GITHUB_API_KEY` environment variable:

```toml
[llm]
api_key = "ghp_..."
model = "github/gpt-4o"
```

### Using your Claude subscription (via Claude Code CLI)

If you have a [Claude Max, Team, or Enterprise](https://claude.ai) subscription, you can use it directly as the LLM provider via the [Claude Code CLI](https://claude.ai/download) — no separate API key purchase required.

1. Install the Claude Code CLI if you haven't already (see [claude.ai/download](https://claude.ai/download)). Verify it's on your PATH:

```bash
claude --version
```

2. Authenticate. You have two options:

   **Option A — Claude Max / Pro subscription (OAuth token):**

   ```bash
   claude setup-token
   export CLAUDE_CODE_OAUTH_TOKEN=<your-token>
   ```

   **Option B — Anthropic API key:**

   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

3. Set the model to a `claude_agent_sdk/` prefixed name in your config:

```toml
[llm]
api_key = ""
model = "claude_agent_sdk/claude-sonnet-4-20250514"
```

4. Run as usual — the CLI handles the rest:

```bash
uv run main.py feed | uv run main.py rate | uv run main.py summarize
```

Available models (depends on your subscription tier):

| Model string                                   | Description                    |
| ---------------------------------------------- | ------------------------------ |
| `claude_agent_sdk/claude-sonnet-4-20250514`    | Claude Sonnet — fast, capable  |
| `claude_agent_sdk/claude-opus-4-1`             | Claude Opus — slower, stronger |

> **Note:** Each LLM call spawns a `claude -p` subprocess, which is heavier than a direct HTTP request. Concurrency is automatically reduced to 2 parallel batches when using `claude_agent_sdk/` models. Wall-clock time for batch operations will be slower than with direct API providers.

## Usage

### TUI (interactive)

Run `uv run main.py` with no arguments to launch the interactive terminal UI.

#### Keyboard shortcuts

| Key | Action                          |
| --- | ------------------------------- |
| `f` | Open Feed screen / Fetch papers |
| `l` | Open Library screen             |
| `s` | Open Settings screen            |
| `q` | Quit                            |

#### Feed screen

| Key      | Action                     |
| -------- | -------------------------- |
| `f`      | Fetch papers from arXiv    |
| `a`      | Run AI relevance filtering |
| `Space`  | Toggle paper selection     |
| `Ctrl+A` | Select/deselect all        |
| `s`      | Summarize selected papers  |
| `d`      | Toggle detail panel        |
| `Escape` | Go back                    |

#### Workflow

1. **Configure** — set your API key, model, and research interests in Settings
2. **Fetch** — pick a category and fetch papers (latest or by date range)
3. **Filter** — press `a` to run AI filtering; papers are scored and sorted by relevance
4. **Select** — use `Space` to pick papers you want summarized
5. **Summarize** — press `s`; each paper's PDF is downloaded, text extracted, and summarized by the AI
6. **Browse** — summaries appear in the Library screen and as markdown files in your output directory

### CLI pipeline

Each pipeline stage is a subcommand. Stages communicate via JSON Lines on stdout/stdin, so you can freely compose them with Unix pipes. Progress and status messages go to stderr; only paper data goes to stdout.

```
uv run main.py feed | uv run main.py rate | uv run main.py summarize
```

#### `feed` — fetch papers

Fetches papers from arXiv and writes them to stdout as JSON Lines. Defaults to the latest announcement window using the categories from your config.

```bash
# Latest papers from config categories
uv run main.py feed

# Specific category, limit results
uv run main.py feed --category hep-th --max-papers 50

# Multiple categories (flag is repeatable)
uv run main.py feed -C hep-ph -C hep-th

# Date range query
uv run main.py feed --start 2026-03-01 --end 2026-03-05

# Include cross-posted papers
uv run main.py feed --cross-posts
```

#### `rate` — score by relevance

Reads papers from stdin, scores each one against your interests file using the configured LLM, and writes the rated papers to stdout sorted by descending score.

```bash
# Rate all papers
uv run main.py feed | uv run main.py rate

# Only pass through papers scoring 7 or above
uv run main.py feed | uv run main.py rate --min-score 7

# Override the model for this run
uv run main.py feed | uv run main.py rate --model github_copilot/gpt-4o-mini
```

#### `summarize` — download and summarize

Reads papers from stdin, downloads each PDF, extracts the text, and generates an AI summary saved to your library. The same papers are written to stdout so the pipeline can continue.

```bash
# Summarize all rated papers
uv run main.py feed | uv run main.py rate | uv run main.py summarize

# Write to a different output directory
uv run main.py feed | uv run main.py rate | uv run main.py summarize --output-dir ~/papers/2026-03
```

#### `export` — convert summaries to HTML

Reads papers from stdin, finds their corresponding markdown summary files in the library, and converts each one to a self-contained HTML file with pre-rendered LaTeX math (PNG images embedded inline — no JavaScript, no CDN). The HTML files are suitable for opening in a browser or attaching to an email. The same papers are written to stdout so the pipeline can continue.

```bash
# Export summaries and open the last one in the browser
uv run main.py feed | uv run main.py rate | uv run main.py summarize | uv run main.py export --open

# Combine all exported summaries into a single digest page
uv run main.py feed | uv run main.py rate | uv run main.py summarize | uv run main.py export --digest --open

# Custom digest title
uv run main.py feed -C hep-ph | uv run main.py rate | uv run main.py summarize \
  | uv run main.py export --digest --digest-title "hep-ph digest 2026-03-06" --open

# Write HTML files to a different directory
uv run main.py feed | uv run main.py rate | uv run main.py summarize | uv run main.py export --output-dir ~/exports
```

HTML files are written alongside the corresponding markdown files, with the same base name and a `.html` extension. In `--digest` mode a `digest_YYYY-MM-DD.html` file is also written to the root of the output directory.

#### Common options

All subcommands accept:

| Flag             | Description                                           |
| ---------------- | ----------------------------------------------------- |
| `--config PATH`  | Use a specific config file instead of the default     |
| `--model MODEL`  | Override the LLM model (`rate` and `summarize` only)  |

#### Full pipeline example

```bash
# Fetch today's hep-ph papers, keep only highly relevant ones, summarize and export to HTML
uv run main.py feed -C hep-ph | uv run main.py rate --min-score 7 | uv run main.py summarize | uv run main.py export --digest --open
```

#### Using with jq

Because stdout is JSON Lines, you can filter and inspect papers at any point with standard tools:

```bash
# See titles and scores after rating
uv run main.py feed | uv run main.py rate | jq -r '"\(.relevance_score) \(.title)"'

# Save rated papers for later
uv run main.py feed | uv run main.py rate > rated.jsonl

# Summarize from a saved file
cat rated.jsonl | uv run main.py summarize
```

### Output structure

```
~/arxiv-coffee-library/
├── library.md                          # Central index of all summaries
├── digest_2026-03-06.html              # Combined digest (from export --digest)
├── hep-ph/
│   ├── 2026-03-03_susy-at-the-lhc.md
│   ├── 2026-03-03_susy-at-the-lhc.html
│   ├── 2026-03-03_dark-matter-searches.md
│   └── 2026-03-03_dark-matter-searches.html
└── hep-th/
    ├── 2026-03-02_string-landscape.md
    └── 2026-03-02_string-landscape.html
```

## Dependencies

- [textual](https://github.com/Textualize/textual) — terminal UI framework
- [arxiv](https://github.com/lukasschwab/arxiv.py) — arXiv API client
- [pymupdf](https://github.com/pymupdf/PyMuPDF) — PDF text extraction
- [litellm](https://github.com/BerriAI/litellm) — unified LLM API
- [httpx](https://github.com/encode/httpx) — async HTTP client (for PDF downloads)
- [matplotlib](https://matplotlib.org/) — LaTeX math rendering for HTML export
- [tomli-w](https://github.com/hukkin/tomli-w) — TOML writing
- [typer](https://github.com/fastapi/typer) — CLI framework

### Optional dependencies

Install with `uv pip install arxiv-coffee[graphics]` to enable image rendering of display math in supported terminals:

- [textual-image](https://github.com/lnqs/textual-image) — inline image rendering in the TUI

## License

MIT
