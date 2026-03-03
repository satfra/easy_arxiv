# Implementation Plan: Image-Based LaTeX Rendering for Block Math

## Goal

Render `$$...$$` (display/block) LaTeX math as actual images via
`matplotlib.mathtext` + `textual-image`, with automatic fallback to the
existing Unicode approach when the terminal doesn't support graphics or when
dependencies are unavailable. Inline math (`$...$`) stays Unicode-only — images
can't be embedded within text flow in Textual's rendering model.

## Architecture Decision

**matplotlib.mathtext + textual-image, optional dependency**

```
$$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$$

  ┌─ matplotlib + textual-image installed? ─────────────┐
  │                                                      │
  │ YES: matplotlib renders LaTeX to PIL Image           │
  │      textual-image displays via Sixel/TGP/Halfcell   │
  │                                                      │
  │ NO:  pylatexenc + unicodeit → Unicode text (current)  │
  └──────────────────────────────────────────────────────┘
```

- **matplotlib.mathtext** renders LaTeX to PNG in memory using the Agg backend.
  No system TeX installation required. Covers ~90% of arXiv math (Greek letters,
  fractions, integrals, sums, superscripts, subscripts, square roots). Does NOT
  support full LaTeX environments (`\begin{align}`, custom macros, `amsmath`).
- **textual-image** provides Textual widgets that display PIL Images in the
  terminal. Auto-detects the best rendering method at import time:
  1. Kitty Terminal Graphics Protocol (pixel-perfect, Kitty only)
  2. Sixel (broadest support: xterm, foot, iTerm2, WezTerm, VS Code, Windows Terminal)
  3. Halfcell (Unicode half-block chars `▀▄` with truecolor — any modern terminal)
  4. Unicode (pure character approximation — works everywhere)
- Both are **optional dependencies** — the base app works without them.

**Why not the alternatives:**
- System TeX + dvipng: Requires external installation, heavyweight
- SymPy preview: Requires system TeX, heavy dependency (~40 MB)
- KaTeX via subprocess: Heavyweight, requires Node.js
- term-image: No Sixel support, not integrated with Textual widgets

**Inline math limitation:** Textual's `Content` class (used by
`_token_to_content` for inline rendering) is fundamentally text-based. There is
no mechanism to embed a widget inside a text flow. Inline math must remain
Unicode-only.

## Implementation Steps

### Step 1: Add optional dependencies to `pyproject.toml`

Add a `graphics` optional dependency group:

```toml
[project.optional-dependencies]
graphics = [
    "matplotlib>=3.8.0",
    "textual-image>=0.8.5",
]
```

Users install with `pip install arxiv-coffee[graphics]` or
`uv sync --extra graphics`. The base app works without them.

Note: `textual-image` pulls in `Pillow` as a transitive dependency.

Run `uv sync --extra graphics` after.

### Step 2: Create `src/arxiv_coffee/terminal_caps.py` — capability detection

Terminal capability probing **must** happen before `App.run()` because Textual
takes over stdin/stdout threads. Both `textual_image.renderable` and
`textual_image.widget` run their detection at import time (terminal protocol
query via escape sequences, cell size measurement via ioctl).

```python
from __future__ import annotations

# Flags set at import time.
HAS_GRAPHICS: bool = False
HAS_MATH_IMAGE: bool = False

try:
    # Importing textual_image.renderable triggers terminal probing.
    # This MUST happen before ArxivCoffeApp.run().
    from textual_image.renderable import Image as _AutoRenderable
    from textual_image.renderable.halfcell import Image as _HalfcellRenderable
    from textual_image.renderable.unicode import Image as _UnicodeRenderable

    HAS_GRAPHICS = _AutoRenderable not in (_HalfcellRenderable, _UnicodeRenderable)

    # Also trigger cell size cache (textual-image needs this before Textual starts)
    from textual_image.widget import Image as _WidgetImage  # noqa: F401

    import matplotlib  # noqa: F401

    HAS_MATH_IMAGE = True
except ImportError:
    pass
```

- `HAS_GRAPHICS` — True if terminal supports Sixel or TGP (actual pixel rendering)
- `HAS_MATH_IMAGE` — True if both `matplotlib` and `textual-image` are installed.
  Even when `HAS_GRAPHICS` is False, `textual-image` falls back to halfcell
  rendering which is better than Unicode text for complex math.

### Step 3: Create `src/arxiv_coffee/latex_render.py` — image rendering

A small module with one public function:

```python
from __future__ import annotations

import io

from PIL import Image


def renderLatexToImage(
    latex: str,
    *,
    dpi: int = 150,
    color: str = "white",
) -> Image.Image:
    """Render a LaTeX math expression to a PIL Image in memory.

    Uses matplotlib's built-in mathtext parser with the Agg backend.
    No system TeX installation required.
    """
    import matplotlib
    matplotlib.use("agg")
    from matplotlib.mathtext import math_to_image

    buf = io.BytesIO()
    math_to_image(f"${latex}$", buf, dpi=dpi, format="png", color=color)
    buf.seek(0)
    return Image.open(buf)
```

Key design choices:
- Lazy import of `matplotlib` inside the function — avoids import-time cost
  (~200 ms) when the function is never called.
- `matplotlib.use("agg")` selects the non-GUI backend (no tkinter/Qt dependency).
- `color="white"` for dark terminal backgrounds (matches typical terminal themes).
- Returns a PIL `Image.Image` that `textual-image` accepts directly in its
  widget constructor.
- `dpi=150` gives good legibility at typical terminal cell sizes. A math
  equation image is typically ~200×50 pixels, occupying ~25×3 terminal cells.
- The input `latex` is the raw content inside `$$...$$` (without delimiters).
  `math_to_image` requires `$`-wrapped input, so we add them.

### Step 4: Modify `src/arxiv_coffee/markdown.py` — image-aware math block

Replace the current `_MarkdownMathBlock` with a version that tries image
rendering first, then falls back to Unicode text:

```python
from textual.app import ComposeResult

from arxiv_coffee.terminal_caps import HAS_MATH_IMAGE


class _MarkdownMathBlock(MarkdownBlock):
    """Renders a display-math block as an image when possible, Unicode otherwise."""

    DEFAULT_CSS = """
    _MarkdownMathBlock {
        margin: 1 0;
        padding: 0 4;
        height: auto;
    }
    """

    def __init__(self, markdown: Markdown, token: Token) -> None:
        super().__init__(markdown, token)
        self._latex = token.content.strip()
        self._use_image = HAS_MATH_IMAGE
        if not self._use_image:
            # No image support — render Unicode text immediately
            self.set_content(Content(latexToUnicode(self._latex)))

    def compose(self) -> ComposeResult:
        if self._use_image:
            try:
                from arxiv_coffee.latex_render import renderLatexToImage
                from textual_image.widget import Image as TerminalImage

                pil_img = renderLatexToImage(self._latex)
                yield TerminalImage(pil_img)
            except Exception:
                # Rendering failed — fall back to Unicode
                self.set_content(Content(latexToUnicode(self._latex)))
        yield from self._blocks
```

How this works:
- `__init__` checks `HAS_MATH_IMAGE` to decide the rendering path. If graphics
  deps are missing, it renders Unicode text immediately (same as before).
- `compose()` is called by Textual when the widget is mounted. If image mode is
  active, it lazily imports `renderLatexToImage` and `textual_image.widget.Image`,
  renders the LaTeX to a PIL Image, and yields a `TerminalImage` widget as a child.
- `MarkdownBlock` extends `Static` which extends `Widget`, so child widget
  composition via `compose()` works normally.
- The try/except ensures that if matplotlib fails to parse the LaTeX (e.g. an
  unsupported command), we fall back gracefully to Unicode text.
- `yield from self._blocks` follows the `MarkdownBlock` pattern for any nested
  blocks (shouldn't happen for math blocks, but keeps the contract).

### Step 5: Import `terminal_caps` early in `app.py`

Add one import at the top of `app.py` to trigger terminal probing before
`app.run()`:

```python
# After the __future__ import, before other imports:
from arxiv_coffee.terminal_caps import HAS_MATH_IMAGE  # noqa: F401
```

This ensures the probing escape sequences are sent and responses captured while
stdin/stdout are still available, before Textual's `app.run()` takes them over.

### Step 6: Run `uv sync --extra graphics` and verify

```bash
uv sync --extra graphics
uv run python -c "
from arxiv_coffee.terminal_caps import HAS_GRAPHICS, HAS_MATH_IMAGE
print(f'Graphics: {HAS_GRAPHICS}, Math image: {HAS_MATH_IMAGE}')
"
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Edit | Add `[project.optional-dependencies] graphics` group |
| `src/arxiv_coffee/terminal_caps.py` | Create | Terminal capability detection (import-time probing) |
| `src/arxiv_coffee/latex_render.py` | Create | `renderLatexToImage()` via matplotlib.mathtext |
| `src/arxiv_coffee/markdown.py` | Edit | `_MarkdownMathBlock` tries image rendering, falls back to Unicode |
| `src/arxiv_coffee/app.py` | Edit | Import `terminal_caps` early to trigger probing |

## What This Gives You

- **Sixel/TGP terminals** (Kitty, foot, iTerm2, WezTerm, VS Code, xterm):
  Pixel-perfect LaTeX rendering for display math
- **Truecolor terminals** (GNOME Terminal, etc.): Half-block character
  approximation (better than Unicode text for complex fractions/integrals)
- **No graphics extras installed**: Unchanged behavior — Unicode text via
  pylatexenc/unicodeit
- **Inline math ($...$)**: Always Unicode text (Textual limitation — can't embed
  widgets in text flow)

## What This Does NOT Do

- No inline math image rendering — Textual's `Content` is text-only
- No full LaTeX support — matplotlib.mathtext is a subset parser
  (no `\begin{align}`, no `amsmath`, no custom macros)
- No TeX installation detection — we don't fall back to system `pdflatex`
- No user-configurable DPI or color — could be added later via config

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| matplotlib is ~30 MB | Optional dependency — only installed with `[graphics]` extra |
| `math_to_image` fails on complex LaTeX | try/except falls back to Unicode; covers ~90% of arXiv math |
| Terminal probing timing | Import `terminal_caps` before `app.run()` — documented textual-image pattern |
| Image flickering on scroll | Known textual-image limitation; math blocks are small (~3 cells tall) so impact is minimal |
| `compose()` override on `_MarkdownMathBlock` | Safe — `MarkdownBlock.compose()` just yields `_blocks`; we add an image widget before that |
| LGPL-3.0 license of textual-image | LGPL allows use as a dependency from any license |
| `matplotlib.use("agg")` conflicts with existing matplotlib usage | Unlikely in a TUI app; "agg" is the standard non-interactive backend |
| Probing fails in non-TTY environments (CI, piped output) | `textual_image` detects non-TTY and falls back to `UnicodeImage`; `HAS_GRAPHICS` is False |

## Testing Strategy

Since there is no test suite yet, manual verification:

1. Install graphics extras: `uv sync --extra graphics`
2. Run the app: `uv run arxiv-coffee`
3. Fetch papers from a math-heavy category (e.g., `hep-ph`, `math.AG`)
4. Generate a summary containing `$$...$$` display math
5. Open the summary and verify display math renders as images
6. Verify inline math (`$...$`) still renders as Unicode text
7. Uninstall graphics extras and verify fallback: `uv sync` (without `--extra`)
8. Re-run and verify display math falls back to Unicode text
9. Test in different terminals: Kitty (TGP), VS Code (Sixel), GNOME Terminal
   (halfcell fallback)
