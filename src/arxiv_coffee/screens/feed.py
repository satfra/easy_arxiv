from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    Label,
    DataTable,
    Select,
    Switch,
    LoadingIndicator,
    ProgressBar,
)

from arxiv_coffee.arxiv_client import (
    fetchLatestPapers,
    fetchPapersByDateRange,
    parseFetchInputs,
)
from arxiv_coffee.config import loadInterests
from arxiv_coffee.copilot_auth import checkLlmAuth
from arxiv_coffee.llm import filterPapersByRelevance
from arxiv_coffee.models import AppConfig, Paper
from arxiv_coffee.summarize_pipeline import PipelineProgress, summarizePapers
from arxiv_coffee.widgets import DualProgressBar, MathMarkdown


# arXiv categories commonly used in HEP and related fields
CATEGORY_OPTIONS: list[tuple[str, str]] = [
    ("hep-ph", "hep-ph"),
    ("hep-th", "hep-th"),
    ("hep-ex", "hep-ex"),
    ("hep-lat", "hep-lat"),
    ("astro-ph.HE", "astro-ph.HE"),
    ("astro-ph.CO", "astro-ph.CO"),
    ("gr-qc", "gr-qc"),
    ("nucl-th", "nucl-th"),
    ("nucl-ex", "nucl-ex"),
    ("quant-ph", "quant-ph"),
    ("cond-mat", "cond-mat"),
    ("math-ph", "math-ph"),
    ("physics.data-an", "physics.data-an"),
]


class FeedScreen(Screen):
    """Paper feed screen -- browse, filter, and summarize arXiv papers."""

    BINDINGS = [
        ("f", "fetchPapers", "Fetch"),
        ("a", "aiFilter", "AI Filter"),
        ("s", "summarizeSelected", "Summarize"),
        ("space", "toggleSelect", "Select"),
        ("ctrl+a", "selectAll", "Select All"),
        ("d", "toggleDetail", "Detail"),
        ("escape", "goBack", "Back"),
    ]

    CSS = """
  FeedScreen {
    layout: vertical;
  }

  .toolbar {
    height: auto;
    min-height: 3;
    padding: 0 1;
    background: $surface;
    dock: top;
  }

  .toolbar-row {
    height: 3;
  }

  .toolbar Label {
    margin: 1 1 0 0;
    color: $text-muted;
  }

  .toolbar Select {
    width: 20;
  }

  .toolbar Input {
    width: 12;
  }

  .toolbar Button {
    margin: 0 0 0 1;
  }

  .toolbar Switch {
    margin: 1 0 0 0;
  }

  .date-inputs {
    height: 0;
    overflow: hidden;
  }

  .date-inputs.visible {
    height: auto;
  }

  .date-inputs Input {
    width: 16;
  }

  .date-inputs Label {
    margin: 1 1 0 1;
  }

  #paper-table {
    height: 1fr;
  }

  #detail-panel {
    height: auto;
    max-height: 16;
    border-top: solid $accent;
    padding: 1 2;
    display: none;
  }

  #detail-panel.visible {
    display: block;
  }

  #detail-title {
    text-style: bold;
    color: $accent;
    margin-bottom: 0;
  }

  #detail-meta {
    color: $text-muted;
    margin-bottom: 1;
  }

  #status-line {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    dock: bottom;
  }

  #loading {
    height: 3;
    display: none;
  }

  #loading.visible {
    display: block;
  }

  #progress-container {
    height: auto;
    padding: 0 1;
    display: none;
  }

  #progress-container.visible {
    display: block;
  }

  #progress-label {
    color: $text-muted;
    height: 1;
  }

  #progress-bar {
    height: 1;
  }

  #summarize-progress {
    height: auto;
    padding: 0 1;
    display: none;
  }

  #summarize-progress.visible {
    display: block;
  }

  #summarize-label {
    color: $text-muted;
    height: 1;
  }
  """

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.papers: list[Paper] = []
        self.selected: set[str] = set()  # Set of arxiv short_ids
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(classes="toolbar"):
            with Horizontal(classes="toolbar-row"):
                yield Label("Category:")
                yield Select(
                    options=CATEGORY_OPTIONS,
                    value=self.config.categories[0]
                    if self.config.categories
                    else "hep-ph",
                    id="category-select",
                    allow_blank=False,
                )
                yield Label("Max:")
                yield Input(
                    value=str(self.config.max_papers),
                    id="max-input",
                    type="integer",
                )
                yield Label("Date range:")
                yield Switch(value=False, id="date-toggle")
                yield Label("Cross-posts:")
                yield Switch(
                    value=self.config.include_cross_posts,
                    id="cross-posts-toggle",
                )
                yield Button("Fetch", variant="primary", id="fetch-btn")
                yield Button("AI Filter", variant="warning", id="filter-btn")
                yield Button("Summarize", variant="success", id="summarize-btn")

            with Horizontal(classes="date-inputs", id="date-inputs"):
                yield Label("From:")
                yield Input(placeholder="YYYY-MM-DD", id="date-start")
                yield Label("To:")
                yield Input(placeholder="YYYY-MM-DD", id="date-end")

        yield LoadingIndicator(id="loading")

        with Vertical(id="progress-container"):
            yield Static("", id="progress-label")
            yield ProgressBar(total=100, show_eta=False, id="progress-bar")

        with Vertical(id="summarize-progress"):
            yield Static("", id="summarize-label")
            yield DualProgressBar(id="summarize-bar")

        table = DataTable(id="paper-table", cursor_type="row")
        table.add_columns("Sel", "Score", "Title", "Authors", "Date", "Categories")
        yield table

        with VerticalScroll(id="detail-panel"):
            yield Static("", id="detail-title")
            yield Static("", id="detail-meta")
            yield MathMarkdown("", id="detail-abstract")

        yield Static(
            "Ready. Press [bold]f[/] to fetch, [bold]space[/] to select, "
            "[bold]a[/] to AI filter, [bold]s[/] to summarize.",
            id="status-line",
        )
        yield Footer()

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------

    def action_fetchPapers(self) -> None:
        if self._busy:
            self.notify("An operation is already in progress.", severity="warning")
            return
        self._doFetch()

    def action_aiFilter(self) -> None:
        if self._busy:
            self.notify("An operation is already in progress.", severity="warning")
            return
        self._doFilter()

    def action_summarizeSelected(self) -> None:
        if self._busy:
            self.notify("An operation is already in progress.", severity="warning")
            return
        self._doSummarize()

    def action_toggleSelect(self) -> None:
        """Toggle selection on the currently highlighted row."""
        table = self.query_one("#paper-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            self._toggleRow(row_key.value)

    def action_selectAll(self) -> None:
        """Toggle all rows selected/unselected."""
        if len(self.selected) == len(self.papers):
            self.selected.clear()
            self._setStatus("All papers deselected.")
        else:
            self.selected = {p.short_id for p in self.papers}
            self._setStatus(f"All {len(self.selected)} papers selected.")
        self._refreshCheckmarks()

    def action_toggleDetail(self) -> None:
        """Toggle the detail panel visibility."""
        panel = self.query_one("#detail-panel")
        panel.toggle_class("visible")

    def action_goBack(self) -> None:
        if self._busy:
            self.notify(
                "Operation in progress. Please wait.",
                severity="warning",
            )
            return
        self.app.pop_screen()

    # -------------------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------------------

    @on(Button.Pressed, "#fetch-btn")
    def onFetch(self) -> None:
        self.action_fetchPapers()

    @on(Button.Pressed, "#filter-btn")
    def onFilter(self) -> None:
        self.action_aiFilter()

    @on(Button.Pressed, "#summarize-btn")
    def onSummarize(self) -> None:
        self.action_summarizeSelected()

    @on(Switch.Changed, "#date-toggle")
    def onDateToggle(self, event: Switch.Changed) -> None:
        """Show/hide date range inputs when the toggle changes."""
        date_inputs = self.query_one("#date-inputs")
        if event.value:
            date_inputs.add_class("visible")
        else:
            date_inputs.remove_class("visible")

    @on(DataTable.RowSelected, "#paper-table")
    def onRowSelected(self, event: DataTable.RowSelected) -> None:
        """Toggle selection on Enter/click."""
        row_key = event.row_key.value
        self._toggleRow(row_key)

    @on(DataTable.RowHighlighted, "#paper-table")
    def onRowHighlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update the detail panel when a row is highlighted."""
        if event.row_key is None:
            return
        row_key = event.row_key.value
        paper = self._getPaper(row_key)
        if paper is None:
            return
        self._updateDetailPanel(paper)

    # -------------------------------------------------------------------
    # Workers
    # -------------------------------------------------------------------

    @work(thread=False)
    async def _doFetch(self) -> None:
        """Fetch papers from arXiv."""
        self._setBusy(True)
        self._showLoading(True)
        self._setStatus("Fetching papers from arXiv...")

        try:
            category = self.query_one("#category-select", Select).value
            max_str = self.query_one("#max-input", Input).value
            use_dates = self.query_one("#date-toggle", Switch).value
            include_cross = self.query_one("#cross-posts-toggle", Switch).value

            start_str = ""
            end_str = ""
            if use_dates:
                start_str = self.query_one("#date-start", Input).value
                end_str = self.query_one("#date-end", Input).value

            try:
                req = parseFetchInputs(
                    category=str(category) if category else "",
                    max_papers_str=max_str,
                    use_dates=use_dates,
                    include_cross_posts=include_cross,
                    start_str=start_str,
                    end_str=end_str,
                    config=self.config,
                )
            except ValueError as exc:
                self.notify(str(exc), severity="error", title="Date Range")
                return

            if req.use_dates:
                assert req.start is not None and req.end is not None
                self.papers = await fetchPapersByDateRange(
                    self.config,
                    req.start,
                    req.end,
                    categories=req.categories,
                    max_results=req.max_papers,
                    include_cross_posts=req.include_cross_posts,
                )
            else:
                self.papers = await fetchLatestPapers(
                    self.config,
                    categories=req.categories,
                    max_results=req.max_papers,
                    include_cross_posts=req.include_cross_posts,
                )

            self.selected.clear()
            self._populateTable()

            if not self.papers:
                self._setStatus("No papers found for this query.")
                self.notify(
                    "No papers found. Try different categories or dates.",
                    severity="warning",
                    title="No Results",
                )
            else:
                self._setStatus(
                    f"Fetched {len(self.papers)} papers. "
                    f"Press [bold]space[/] to select, [bold]a[/] to AI filter."
                )

        except Exception as e:
            self.notify(f"Fetch failed: {e}", severity="error", title="Network Error")
            self._setStatus(f"Fetch error: {e}")
        finally:
            self._showLoading(False)
            self._setBusy(False)

    @work(thread=False)
    async def _doFilter(self) -> None:
        """Run AI relevance filtering on fetched papers."""
        if not self.papers:
            self.notify("No papers to filter. Fetch first.", severity="warning")
            return

        if not await self._ensureLlmAuth():
            return

        # Load interests
        interests = loadInterests(self.config)

        if not interests:
            self.notify(
                "No interests file found. Write your interests in Settings first.",
                severity="warning",
                title="Missing Interests",
            )
            return

        batch_size = 5
        total_batches = (len(self.papers) + batch_size - 1) // batch_size

        self._setBusy(True)
        self._showProgress(True, total_batches)
        self._setStatus(
            f"AI filtering {len(self.papers)} papers using {self.config.model}..."
        )

        try:

            def _onBatchDone(done: int, total: int) -> None:
                self._updateProgress(
                    done,
                    total,
                    f"AI filtering — batch {done}/{total} "
                    f"({len(self.papers)} papers, {self.config.model})",
                )

            self.papers = await filterPapersByRelevance(
                self.papers,
                interests,
                self.config,
                batch_size=batch_size,
                on_batch_done=_onBatchDone,
            )
            self._populateTable()
            top_score = max(
                (
                    p.relevance_score
                    for p in self.papers
                    if p.relevance_score is not None
                ),
                default=0,
            )
            self._setStatus(
                f"Filtered {len(self.papers)} papers. "
                f"Top score: {top_score:.0f}/10. "
                f"Select papers with [bold]space[/], then [bold]s[/] to summarize."
            )
        except Exception as e:
            self.notify(f"AI filter failed: {e}", severity="error", title="LLM Error")
            self._setStatus(f"Filter error: {e}")
        finally:
            self._showProgress(False, 0)
            self._setBusy(False)

    @work(thread=False)
    async def _doSummarize(self) -> None:
        """Download, extract, and summarize selected papers concurrently."""
        if not self.selected:
            self.notify(
                "No papers selected. Use Space to toggle selection.",
                severity="warning",
            )
            return

        if not await self._ensureLlmAuth():
            return

        papers_to_summarize = [p for p in self.papers if p.short_id in self.selected]
        total = len(papers_to_summarize)

        self._setBusy(True)
        self._setStatus(f"Summarizing {total} paper(s)...")

        # Show the dual-segment progress bar.
        container = self.query_one("#summarize-progress")
        bar = self.query_one("#summarize-bar", DualProgressBar)
        label = self.query_one("#summarize-label", Static)
        bar.updateCounts(downloading=0, summarizing=0, done=0, total=total)
        label.update(f"Starting summarization of {total} paper(s)...")
        container.add_class("visible")

        def _onProgress(progress: PipelineProgress) -> None:
            """Map pipeline progress to UI widgets."""
            bar.updateCounts(
                downloading=progress.downloading,
                summarizing=progress.summarizing,
                done=progress.done,
                total=progress.total,
            )
            parts: list[str] = []
            if progress.downloading:
                parts.append(f"Downloading: {progress.downloading}")
            if progress.summarizing:
                parts.append(f"Summarizing: {progress.summarizing}")
            parts.append(f"Done: {progress.done}/{progress.total}")
            label.update(" | ".join(parts))

        result = await summarizePapers(
            papers_to_summarize,
            self.config,
            on_progress=_onProgress,
        )

        summary = result.summary + f". Output: {self.config.output_dir}"
        label.update(summary)
        self._setBusy(False)
        self._setStatus(summary)
        self.notify(summary, title="Summarization Complete")

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    async def _ensureLlmAuth(self) -> bool:
        """Verify that LLM credentials are available before making calls.

        For most providers this checks for a non-empty API key. For
        github_copilot/ models it checks for a cached OAuth token and
        shows the interactive device-flow modal when one is missing.

        Returns True if auth is ready, False if the user cancelled or
        auth failed.
        """
        ready, reason = checkLlmAuth(self.config.model, self.config.api_key)
        if ready:
            return True

        if reason == "claude_cli_not_found":
            self.notify(
                "The 'claude' CLI is not installed. See https://claude.ai/download",
                severity="error",
                title="Claude CLI Missing",
            )
            return False

        if reason == "claude_agent_sdk_auth_needed":
            self.notify(
                "Set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN in your environment.",
                severity="error",
                title="Claude CLI Auth",
            )
            return False

        if reason == "copilot_auth_needed":
            from arxiv_coffee.screens.copilot_auth import CopilotAuthScreen

            result = await self.app.push_screen_wait(CopilotAuthScreen())
            if not result:
                self.notify(
                    "Copilot authentication cancelled.",
                    severity="warning",
                )
                return False
            return True

        if reason == "no_api_key":
            self.notify(
                "No API key configured. Go to Settings (press Escape, then s).",
                severity="error",
                title="Missing API Key",
            )
            return False

        return False

    def _populateTable(self) -> None:
        """Fill the DataTable with current papers."""
        table = self.query_one("#paper-table", DataTable)
        table.clear()

        for paper in self.papers:
            check = "[bold green]X[/]" if paper.short_id in self.selected else " "
            score = (
                f"{paper.relevance_score:.0f}"
                if paper.relevance_score is not None
                else "-"
            )
            authors = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " ..."
            date = paper.published.strftime("%Y-%m-%d")
            cats = ", ".join(paper.categories[:2])

            table.add_row(
                check,
                score,
                paper.title[:80],
                authors[:40],
                date,
                cats,
                key=paper.short_id,
            )

    def _toggleRow(self, short_id: str) -> None:
        """Toggle a paper's selection state."""
        if short_id in self.selected:
            self.selected.discard(short_id)
        else:
            self.selected.add(short_id)
        self._refreshCheckmarks()
        count = len(self.selected)
        self._setStatus(
            f"{count} paper(s) selected." if count else "No papers selected."
        )

    def _refreshCheckmarks(self) -> None:
        """Update the checkbox column for all rows."""
        table = self.query_one("#paper-table", DataTable)
        check_col = table.columns[list(table.columns.keys())[0]]
        for row_key in table.rows:
            sid = row_key.value
            mark = "[bold green]X[/]" if sid in self.selected else " "
            table.update_cell(row_key, check_col.key, mark)

    def _updateDetailPanel(self, paper: Paper) -> None:
        """Update the detail panel content for the given paper."""
        panel = self.query_one("#detail-panel")
        panel.add_class("visible")

        self.query_one("#detail-title", Static).update(paper.title)

        authors = ", ".join(paper.authors[:5])
        if len(paper.authors) > 5:
            authors += f" + {len(paper.authors) - 5} more"
        meta = (
            f"[bold]arXiv:[/bold] {paper.short_id}  |  "
            f"[bold]Date:[/bold] {paper.published.strftime('%Y-%m-%d')}  |  "
            f"[bold]Authors:[/bold] {authors}"
        )
        if paper.relevance_score is not None:
            meta += f"  |  [bold]Relevance:[/bold] {paper.relevance_score:.0f}/10"
        if paper.relevance_reason:
            meta += f"\n[italic]{paper.relevance_reason}[/italic]"
        self.query_one("#detail-meta", Static).update(meta)

        self.query_one("#detail-abstract", MathMarkdown).update(
            f"**Abstract:** {paper.abstract}"
        )

    def _getPaper(self, short_id: str) -> Paper | None:
        """Find a paper by short_id."""
        for p in self.papers:
            if p.short_id == short_id:
                return p
        return None

    def _showLoading(self, show: bool) -> None:
        loading = self.query_one("#loading", LoadingIndicator)
        if show:
            loading.add_class("visible")
        else:
            loading.remove_class("visible")

    def _showProgress(self, show: bool, total: int) -> None:
        container = self.query_one("#progress-container")
        bar = self.query_one("#progress-bar", ProgressBar)
        if show:
            bar.update(total=total, progress=0)
            container.add_class("visible")
        else:
            container.remove_class("visible")

    def _updateProgress(self, current: float, total: int, label: str) -> None:
        self.query_one("#progress-label", Static).update(label)
        bar = self.query_one("#progress-bar", ProgressBar)
        bar.update(total=total, progress=current)

    def _setBusy(self, busy: bool) -> None:
        self._busy = busy
        # Disable/enable action buttons
        for btn_id in ("#fetch-btn", "#filter-btn", "#summarize-btn"):
            self.query_one(btn_id, Button).disabled = busy

    def _setStatus(self, text: str) -> None:
        self.query_one("#status-line", Static).update(text)
