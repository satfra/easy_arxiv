from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Input, DataTable

from arxiv_coffe.library import parseSummaryFile
from arxiv_coffe.models import AppConfig
from arxiv_coffe.screens.summary import SummaryScreen


class LibraryScreen(Screen):
    """Browse previously summarized papers."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("/", "focusSearch", "Search"),
    ]

    CSS = """
  LibraryScreen {
    layout: vertical;
  }

  #search-bar {
    height: 3;
    padding: 0 1;
    background: $surface;
    dock: top;
  }

  #search-bar Input {
    width: 1fr;
  }

  #lib-table {
    height: 1fr;
  }

  #lib-status {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    dock: bottom;
  }

  #empty-msg {
    padding: 2 4;
    color: $text-muted;
    text-style: italic;
  }
  """

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.entries: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="search-bar"):
            yield Input(
                placeholder="Search by title, category, or arXiv ID...",
                id="search-input",
            )

        table = DataTable(id="lib-table", cursor_type="row")
        table.add_columns("Date", "Category", "arXiv", "Title")
        yield table

        yield Static("", id="lib-status")
        yield Footer()

    def on_mount(self) -> None:
        self._loadEntries()
        self._populateTable()

    def on_screen_resume(self) -> None:
        """Re-scan entries when returning to this screen."""
        self._loadEntries()
        search_text = self.query_one("#search-input", Input).value
        self._populateTable(search_text)

    def _loadEntries(self) -> None:
        """Scan the output directory for summary files."""
        self.entries.clear()
        output_dir = self.config.output_dir

        if not output_dir.exists():
            return

        for md_file in sorted(output_dir.rglob("*.md"), reverse=True):
            if md_file.name == "library.md":
                continue
            if md_file.parent == output_dir:
                continue

            entry = parseSummaryFile(md_file)
            if entry is not None:
                self.entries.append(entry)

        # Sort by date descending
        self.entries.sort(key=lambda e: e["date"], reverse=True)

    def _populateTable(self, filter_text: str = "") -> None:
        """Fill the table, optionally filtered by search text."""
        table = self.query_one("#lib-table", DataTable)
        table.clear()

        query = filter_text.lower().strip()
        shown = 0

        for entry in self.entries:
            if query:
                searchable = (
                    f"{entry['title']} {entry['category']} {entry['short_id']} {entry['date']}"
                ).lower()
                if query not in searchable:
                    continue

            table.add_row(
                entry["date"],
                entry["category"],
                entry["short_id"],
                entry["title"][:80],
                key=str(entry["path"]),
            )
            shown += 1

        status = f"{shown} summaries"
        if query:
            status += f" (filtered from {len(self.entries)} total)"
        self.query_one("#lib-status", Static).update(status)

    def action_focusSearch(self) -> None:
        self.query_one("#search-input", Input).focus()

    @on(Input.Changed, "#search-input")
    def onSearchChanged(self, event: Input.Changed) -> None:
        self._populateTable(event.value)

    @on(DataTable.RowSelected, "#lib-table")
    def onRowSelected(self, event: DataTable.RowSelected) -> None:
        """Open the summary file in the viewer."""
        file_path = Path(str(event.row_key.value))
        if file_path.exists():
            self.app.push_screen(SummaryScreen(file_path))
        else:
            self.notify(f"File not found: {file_path}", severity="error")
