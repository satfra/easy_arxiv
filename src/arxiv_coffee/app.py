from __future__ import annotations

from arxiv_coffee.terminal_caps import HAS_MATH_IMAGE  # noqa: F401

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Button

from arxiv_coffee.config import ensureConfigExists, loadConfig
from arxiv_coffee.models import AppConfig
from arxiv_coffee.screens.feed import FeedScreen
from arxiv_coffee.screens.library_screen import LibraryScreen
from arxiv_coffee.screens.settings import SettingsScreen


LOGO = r"""
   __ _ _ ____  _(_)_   __       ___ ___  / _| / _| ___  ___
  / _` | '__\ \/ / \ \ / / __   / __/ _ \| |_ | |_ / _ \/ _ \
 | (_| | |   >  <| |\ V / ____ | (_| (_) |  _||  _|  __/  __/
  \__,_|_|  /_/\_\_| \_/ ______ \___\___/|_|  |_|  \___|\___|
"""


class HomeScreen(Vertical):
    """Home screen widget shown on app launch."""

    CSS = """
  HomeScreen {
    align: center middle;
  }

  #logo {
    text-align: center;
    color: $accent;
    margin-bottom: 1;
  }

  #subtitle {
    text-align: center;
    color: $text-muted;
    margin-bottom: 2;
  }

  .home-buttons {
    align: center middle;
    height: auto;
    width: auto;
  }

  .home-buttons Button {
    margin: 0 1;
    min-width: 20;
  }

  #config-info {
    text-align: center;
    color: $text-disabled;
    margin-top: 2;
  }

  #no-key-warning {
    text-align: center;
    color: $warning;
    margin-top: 1;
  }
  """

    def compose(self) -> ComposeResult:
        yield Static(LOGO, id="logo")
        yield Static(
            "Browse, filter, and summarize arXiv papers with AI",
            id="subtitle",
        )
        with Horizontal(classes="home-buttons"):
            yield Button("Feed", variant="primary", id="home-feed")
            yield Button("Library", variant="default", id="home-library")
            yield Button("Settings", variant="default", id="home-settings")
        yield Static("", id="config-info")
        yield Static("", id="no-key-warning")


class ArxivCoffeApp(App):
    """Main TUI application for arxiv-coffee."""

    TITLE = "arxiv-coffee"
    SUB_TITLE = "arXiv paper browser & summarizer"

    BINDINGS = [
        Binding("f", "openFeed", "Feed", show=True),
        Binding("l", "openLibrary", "Library", show=True),
        Binding("s", "openSettings", "Settings", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    CSS = """
  Screen {
    background: $background;
  }
  """

    def __init__(self) -> None:
        super().__init__()
        self.config: AppConfig = AppConfig()
        self.is_new_config = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield HomeScreen()
        yield Footer()

    def on_mount(self) -> None:
        self.config, self.is_new_config = ensureConfigExists()
        self._updateHomeInfo()

        if self.is_new_config or not self.config.api_key:
            self.notify(
                "Welcome! Configure your API key and preferences in Settings.",
                title="First Run",
                timeout=8,
            )
            # Auto-open Settings on first run so the user can configure immediately
            self.set_timer(0.3, self.action_openSettings)

    def _updateHomeInfo(self) -> None:
        """Update the home screen with current config info."""
        try:
            info = self.query_one("#config-info", Static)
            info.update(
                f"Model: {self.config.model}  |  "
                f"Categories: {', '.join(self.config.categories)}  |  "
                f"Output: {self.config.output_dir}"
            )

            warning = self.query_one("#no-key-warning", Static)
            if not self.config.api_key:
                warning.update("No API key set. Go to Settings to configure.")
            else:
                warning.update("")
        except Exception as exc:
            self.log.warning(f"Failed to update home info: {exc}")

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------

    def action_openFeed(self) -> None:
        # Reload config in case it was changed in settings
        self.config = loadConfig()
        self.push_screen(FeedScreen(self.config))

    def action_openLibrary(self) -> None:
        self.config = loadConfig()
        self.push_screen(LibraryScreen(self.config))

    def action_openSettings(self) -> None:
        self.config = loadConfig()
        self.push_screen(
            SettingsScreen(self.config),
            callback=self._onSettingsClose,
        )

    def _onSettingsClose(self, _result: object = None) -> None:
        """Refresh config when settings screen is closed."""
        self.config = loadConfig()
        self._updateHomeInfo()

    # -------------------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------------------

    @on(Button.Pressed, "#home-feed")
    def onFeedBtn(self) -> None:
        self.action_openFeed()

    @on(Button.Pressed, "#home-library")
    def onLibraryBtn(self) -> None:
        self.action_openLibrary()

    @on(Button.Pressed, "#home-settings")
    def onSettingsBtn(self) -> None:
        self.action_openSettings()


def run() -> None:
    """Entry point for the arxiv-coffee TUI."""
    app = ArxivCoffeApp()
    app.run()


if __name__ == "__main__":
    run()
