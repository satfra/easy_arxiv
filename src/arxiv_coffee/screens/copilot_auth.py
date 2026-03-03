from __future__ import annotations

import asyncio
import webbrowser

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, LoadingIndicator, Static

from arxiv_coffee.copilot_auth import runDeviceFlow


class CopilotAuthScreen(ModalScreen[bool]):
    """Modal that runs the GitHub Copilot OAuth device flow.

    Displays the device code and verification URL, polls in the
    background, and dismisses with True on success or False on
    cancel / failure.
    """

    CSS = """
    CopilotAuthScreen {
        align: center middle;
    }

    #copilot-auth-dialog {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2 3;
    }

    #copilot-auth-title {
        text-style: bold;
        color: $accent;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #copilot-auth-instructions {
        text-align: center;
        margin-bottom: 1;
    }

    #copilot-auth-code {
        text-style: bold;
        text-align: center;
        color: $warning;
        width: 100%;
        margin-bottom: 1;
    }

    #copilot-auth-url {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #copilot-auth-status {
        text-align: center;
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }

    #copilot-auth-loading {
        height: 3;
    }

    #copilot-auth-buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #copilot-auth-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._poll_task: asyncio.Task[str] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="copilot-auth-dialog"):
            yield Static("GitHub Copilot Authentication", id="copilot-auth-title")
            yield Static(
                "Requesting device code from GitHub...",
                id="copilot-auth-instructions",
            )
            yield Static("", id="copilot-auth-code")
            yield Static("", id="copilot-auth-url")
            yield LoadingIndicator(id="copilot-auth-loading")
            yield Static("", id="copilot-auth-status")
            with Vertical(id="copilot-auth-buttons"):
                yield Button("Open Browser", variant="primary", id="open-browser-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        """Start the device flow as soon as the modal is shown."""
        self.query_one("#open-browser-btn", Button).disabled = True
        self._startAuth()

    @work(thread=False)
    async def _startAuth(self) -> None:
        """Request a device code and start polling for authorisation."""
        try:
            user_code, verification_uri, poll_task = await runDeviceFlow()
        except Exception as e:
            self.query_one("#copilot-auth-instructions", Static).update(
                f"Failed to start authentication: {e}"
            )
            self.query_one("#copilot-auth-loading").display = False
            return

        self._verification_uri = verification_uri
        self._poll_task = poll_task

        self.query_one("#copilot-auth-instructions", Static).update(
            "Enter this code on GitHub to authenticate:"
        )
        self.query_one("#copilot-auth-code", Static).update(user_code)
        self.query_one("#copilot-auth-url", Static).update(verification_uri)
        self.query_one("#copilot-auth-status", Static).update(
            "Waiting for authorisation..."
        )
        self.query_one("#open-browser-btn", Button).disabled = False

        try:
            await poll_task
            self.query_one("#copilot-auth-status", Static).update(
                "Authenticated successfully!"
            )
            self.query_one("#copilot-auth-loading").display = False
            # Short delay so the user sees the success message
            await asyncio.sleep(1)
            self.dismiss(True)
        except Exception as e:
            self.query_one("#copilot-auth-status", Static).update(
                f"Authentication failed: {e}"
            )
            self.query_one("#copilot-auth-loading").display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "open-browser-btn":
            if hasattr(self, "_verification_uri"):
                webbrowser.open(self._verification_uri)
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel the auth flow and dismiss."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self.dismiss(False)
