from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Markdown


class SummaryScreen(Screen):
    """Displays a paper summary markdown file."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("q", "app.pop_screen", "Back"),
    ]

    CSS = """
  SummaryScreen {
    layout: vertical;
  }

  #summary-scroll {
    height: 1fr;
    padding: 1 2;
  }

  #summary-path {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    background: $surface;
    dock: bottom;
  }
  """

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="summary-scroll"):
            yield Markdown("", id="summary-content")
        yield Static(str(self.file_path), id="summary-path")
        yield Footer()

    def on_mount(self) -> None:
        try:
            content = self.file_path.read_text(encoding="utf-8")
        except OSError as e:
            content = f"**Error:** Could not read file: {e}"
        self.query_one("#summary-content", Markdown).update(content)
