from __future__ import annotations

from rich.style import Style
from rich.text import Text

from textual.reactive import reactive
from textual.widget import Widget


# Unicode bar characters (same as Textual's internal bar renderable).
_BAR = "\u2501"  # ━  full-width bar segment
_HALF_LEFT = "\u257a"  # ╺  left half-bar cap
_HALF_RIGHT = "\u2578"  # ╸  right half-bar cap

# Default segment colors.
_STYLE_DOWNLOAD = Style(color="cyan")
_STYLE_SUMMARIZE = Style(color="yellow")
_STYLE_DONE = Style(color="green")
_STYLE_BG = Style(color="grey37")


class DualProgressBar(Widget, can_focus=False):
    """A three-segment progress bar showing download / summarize / done counts.

    Each segment occupies a proportional fraction of the bar width based on
    the number of papers in that state relative to *total*.  The remaining
    width is rendered in a dim background style for papers not yet started.
    """

    DEFAULT_CSS = """
    DualProgressBar {
        height: 1;
        width: 1fr;
    }
    """

    downloading: reactive[int] = reactive(0)
    summarizing: reactive[int] = reactive(0)
    done: reactive[int] = reactive(0)
    total: reactive[int] = reactive(0)

    # --- Public API --------------------------------------------------------

    def updateCounts(
        self,
        *,
        downloading: int,
        summarizing: int,
        done: int,
        total: int,
    ) -> None:
        """Set all four counters in one call and trigger a re-render."""
        self.downloading = downloading
        self.summarizing = summarizing
        self.done = done
        self.total = total

    # --- Rendering ---------------------------------------------------------

    def render(self) -> Text:
        """Build a Rich Text bar with three colored segments."""
        width = self.size.width
        if width <= 0 or self.total <= 0:
            return Text(_BAR * max(width, 0), style=_STYLE_BG)

        # Compute proportional column widths for each segment.
        dl_cols = self.downloading / self.total * width
        sum_cols = self.summarizing / self.total * width
        done_cols = self.done / self.total * width

        segments: list[tuple[float, Style]] = [
            (done_cols, _STYLE_DONE),
            (dl_cols, _STYLE_DOWNLOAD),
            (sum_cols, _STYLE_SUMMARIZE),
        ]

        bar = Text()
        used = 0.0
        for cols, style in segments:
            chars = _renderSegment(cols)
            if chars:
                bar.append(chars, style=style)
                used += len(chars)

        # Fill remaining width with background.
        remaining = width - int(used)
        if remaining > 0:
            bar.append(_BAR * remaining, style=_STYLE_BG)

        return bar


def _renderSegment(cols: float) -> str:
    """Convert a fractional column width into bar characters.

    Uses half-cell precision: values between 0.25 and 0.75 produce a
    half-bar cap; values >= 0.75 round up to a full bar character.
    """
    if cols < 0.25:
        return ""

    # Round to nearest half.
    halved = round(cols * 2) / 2
    full = int(halved)
    has_half = (halved - full) >= 0.5

    parts: list[str] = []
    if full > 0:
        parts.append(_BAR * full)
    if has_half:
        parts.append(_HALF_RIGHT)

    return "".join(parts)
