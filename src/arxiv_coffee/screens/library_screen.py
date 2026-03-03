from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Header, Footer, Static, Input, Button, DataTable, Label

from arxiv_coffee.library import deleteFromLibrary, parseSummaryFile
from arxiv_coffee.models import AppConfig
from arxiv_coffee.screens.summary import SummaryScreen

# Markdown logo (simplified M-down-arrow glyph) used as the button label.
_OBSIDIAN_LABEL = "\u24c2 Obsidian"


def _isObsidianInstalled() -> bool:
    """Return True if Obsidian appears to be installed."""
    if shutil.which("obsidian"):
        return True
    if sys.platform == "darwin":
        return Path("/Applications/Obsidian.app").exists()
    return False


def _openInObsidian(vault_path: Path) -> None:
    """Open a directory as an Obsidian vault via the obsidian:// URI scheme."""
    uri = f"obsidian://open?path={quote(str(vault_path.resolve()), safe='')}"
    if sys.platform == "darwin":
        subprocess.Popen(["open", uri])
    elif sys.platform == "win32":
        import os

        os.startfile(uri)  # type: ignore[attr-defined]  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", uri])


class _ConfirmDeleteScreen(ModalScreen[bool]):
    """Modal dialog asking the user to confirm a deletion."""

    CSS = """
    _ConfirmDeleteScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }

    #confirm-dialog Label {
        width: 100%;
        margin: 0 0 1 0;
    }

    #confirm-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"Delete [bold]{self._title}[/bold]?")
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="default", id="confirm-no")

    @on(Button.Pressed, "#confirm-yes")
    def onConfirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def onCancel(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class LibraryScreen(Screen):
    """Browse previously summarized papers."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("/", "focusSearch", "Search"),
        ("d", "deleteEntry", "Delete"),
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

  #search-bar Button {
    margin: 0 0 0 1;
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

        with Horizontal(id="search-bar"):
            yield Input(
                placeholder="Search by title, category, or arXiv ID...",
                id="search-input",
            )
            if _isObsidianInstalled():
                yield Button(_OBSIDIAN_LABEL, variant="default", id="obsidian-btn")

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

    def action_deleteEntry(self) -> None:
        """Delete the currently highlighted library entry."""
        table = self.query_one("#lib-table", DataTable)
        if table.row_count == 0:
            self.notify("Nothing to delete.", severity="warning")
            return

        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        file_path = Path(str(row_key.value))

        # Find the entry title for the confirmation dialog.
        title = file_path.stem
        for entry in self.entries:
            if entry["path"] == file_path:
                title = entry["title"]
                break

        def _onConfirm(confirmed: bool) -> None:
            if not confirmed:
                return
            try:
                deleteFromLibrary(file_path, self.config.output_dir)
                self.notify(f"Deleted: {title}")
            except OSError as exc:
                self.notify(f"Delete failed: {exc}", severity="error")
                return
            self._loadEntries()
            search_text = self.query_one("#search-input", Input).value
            self._populateTable(search_text)

        self.app.push_screen(_ConfirmDeleteScreen(title), callback=_onConfirm)

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

    @on(Button.Pressed, "#obsidian-btn")
    def onObsidianOpen(self) -> None:
        """Open the library output directory in Obsidian."""
        output_dir = self.config.output_dir
        if not output_dir.exists():
            self.notify("Output directory does not exist yet.", severity="warning")
            return
        try:
            _openInObsidian(output_dir)
            self.notify("Opening library in Obsidian...")
        except OSError as exc:
            self.notify(f"Failed to open Obsidian: {exc}", severity="error")
