from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    Label,
    TextArea,
)

from arxiv_coffee.config import saveConfig
from arxiv_coffee.models import AppConfig


class SettingsScreen(Screen):
    """Configuration editor screen."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    CSS = """
  SettingsScreen {
    layout: vertical;
  }

  #settings-scroll {
    height: 1fr;
  }

  .settings-form {
    padding: 1 2;
    max-width: 100;
    height: auto;
  }

  .form-group {
    height: auto;
    margin-bottom: 1;
  }

  .form-label {
    color: $text-muted;
    margin-bottom: 0;
  }

  .form-hint {
    color: $text-disabled;
    text-style: italic;
  }

  .section-title {
    color: $accent;
    text-style: bold;
    margin-top: 1;
    margin-bottom: 1;
  }

  .button-bar {
    margin-top: 1;
    height: 3;
  }

  .button-bar Button {
    margin-right: 1;
  }

  #interests-area {
    height: 12;
  }

  #status-bar {
    color: $success;
    margin-top: 1;
    height: 1;
  }
  """

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="settings-scroll"):
            with Vertical(classes="settings-form"):
                yield Static("LLM Settings", classes="section-title")

                with Vertical(classes="form-group"):
                    yield Label("API Key", classes="form-label")
                    yield Input(
                        value=self.config.api_key,
                        placeholder="sk-...",
                        password=True,
                        id="api-key",
                    )

                with Vertical(classes="form-group"):
                    yield Label("Model", classes="form-label")
                    yield Static(
                        "litellm format: openai/gpt-4o, anthropic/claude-sonnet-4-20250514, etc.",
                        classes="form-hint",
                    )
                    yield Input(value=self.config.model, id="model")

                with Vertical(classes="form-group"):
                    yield Label("Base URL (optional)", classes="form-label")
                    yield Input(
                        value=self.config.base_url,
                        placeholder="https://api.example.com/v1",
                        id="base-url",
                    )

                with Vertical(classes="form-group"):
                    yield Label("Requests per minute", classes="form-label")
                    yield Static(
                        "0 = unlimited (provider default)",
                        classes="form-hint",
                    )
                    yield Input(
                        value=str(self.config.requests_per_minute),
                        id="requests-per-minute",
                        type="integer",
                    )

                yield Static("arXiv Settings", classes="section-title")

                with Vertical(classes="form-group"):
                    yield Label("Categories (comma-separated)", classes="form-label")
                    yield Static(
                        "e.g. hep-ph, hep-th, hep-ex, hep-lat, astro-ph.HE",
                        classes="form-hint",
                    )
                    yield Input(
                        value=", ".join(self.config.categories),
                        id="categories",
                    )

                with Vertical(classes="form-group"):
                    yield Label("Max papers per fetch", classes="form-label")
                    yield Input(
                        value=str(self.config.max_papers),
                        id="max-papers",
                        type="integer",
                    )

                yield Static("Paths", classes="section-title")

                with Vertical(classes="form-group"):
                    yield Label("Output directory", classes="form-label")
                    yield Input(
                        value=str(self.config.output_dir),
                        id="output-dir",
                    )

                with Vertical(classes="form-group"):
                    yield Label("Interests file", classes="form-label")
                    yield Input(
                        value=str(self.config.interests_file),
                        id="interests-file",
                    )

                yield Static("Research Interests", classes="section-title")
                yield Static(
                    "Describe your interests below. The AI uses this to rank papers.",
                    classes="form-hint",
                )
                yield TextArea(id="interests-area")

                with Horizontal(classes="button-bar"):
                    yield Button("Save", variant="primary", id="save-btn")
                    yield Button("Back", variant="default", id="back-btn")

                yield Static("", id="status-bar")

        yield Footer()

    def on_mount(self) -> None:
        """Load the interests file content into the text area."""
        interests_path = self.config.interests_file
        area = self.query_one("#interests-area", TextArea)
        if interests_path.exists():
            try:
                area.load_text(interests_path.read_text(encoding="utf-8"))
            except OSError:
                area.load_text(
                    "# My Research Interests\n\nDescribe your interests here.\n"
                )
        else:
            area.load_text("# My Research Interests\n\nDescribe your interests here.\n")

    @on(Button.Pressed, "#save-btn")
    def handleSave(self) -> None:
        """Read all form fields, validate, and save config + interests file."""
        api_key = self.query_one("#api-key", Input).value.strip()
        model = self.query_one("#model", Input).value.strip()
        base_url = self.query_one("#base-url", Input).value.strip()
        rpm_str = self.query_one("#requests-per-minute", Input).value.strip()

        cats_raw = self.query_one("#categories", Input).value
        categories = [c.strip() for c in cats_raw.split(",") if c.strip()]

        max_papers_str = self.query_one("#max-papers", Input).value.strip()
        output_dir_str = self.query_one("#output-dir", Input).value.strip()
        interests_str = self.query_one("#interests-file", Input).value.strip()

        # --- Validation ---
        warnings: list[str] = []

        if not api_key:
            warnings.append("API key is empty \u2014 AI features won't work.")

        if not model:
            warnings.append("Model is empty \u2014 using default.")
            model = "openai/gpt-4o"

        if not categories:
            warnings.append("No categories \u2014 defaulting to hep-ph.")
            categories = ["hep-ph"]

        try:
            max_papers = int(max_papers_str)
            if max_papers < 1:
                raise ValueError
        except ValueError:
            warnings.append("Invalid max papers \u2014 defaulting to 50.")
            max_papers = 50

        try:
            requests_per_minute = int(rpm_str) if rpm_str else 0
            if requests_per_minute < 0:
                raise ValueError
        except ValueError:
            warnings.append("Invalid requests/min \u2014 defaulting to 0 (unlimited).")
            requests_per_minute = 0

        if not output_dir_str:
            warnings.append("Output dir is empty \u2014 using ./output.")
            output_dir_str = "./output"
        output_dir = Path(output_dir_str)

        if not interests_str:
            warnings.append("Interests file path is empty \u2014 using default.")
            interests_str = str(
                Path.home() / ".config" / "arxiv-coffee" / "interests.md"
            )
        interests_file = Path(interests_str)

        # --- Apply ---
        self.config.api_key = api_key
        self.config.model = model
        self.config.base_url = base_url
        self.config.requests_per_minute = requests_per_minute
        self.config.categories = categories
        self.config.max_papers = max_papers
        self.config.output_dir = output_dir
        self.config.interests_file = interests_file

        # Save config
        saveConfig(self.config)

        # Save interests file
        interests_text = self.query_one("#interests-area", TextArea).text
        self.config.interests_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.interests_file.write_text(interests_text, encoding="utf-8")

        # Show results
        if warnings:
            for w in warnings:
                self.notify(w, severity="warning", title="Settings")
        self.query_one("#status-bar", Static).update("Settings saved.")
        self.notify("Settings saved successfully.", title="Settings")

    @on(Button.Pressed, "#back-btn")
    def handleBack(self) -> None:
        self.app.pop_screen()
