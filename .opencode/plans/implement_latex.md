# Implementation Plan: LaTeX Math Rendering in arxiv-coffee TUI

## Goal

Render `$...$` (inline) and `$$...$$` (block) LaTeX math as readable Unicode
in the Textual Markdown widgets used by FeedScreen and SummaryScreen.

## Architecture Decision

**Hybrid approach: pylatexenc + unicodeit**

- **pylatexenc** handles the heavy lifting: converts LaTeX commands to Unicode
  (`\alpha` -> `a`, `\frac{a}{b}` -> `a/b`, `\sqrt{x}` -> `√(x)`), handles
  `\mathrm`, `\textbf`, accented characters, and never crashes on malformed input.
- **unicodeit** runs as a post-processor *only on math content* (not prose) to
  convert `^2` -> `²`, `_i` -> `ᵢ` for better visual quality.
- Neither library has runtime dependencies. Combined overhead is ~1.2 MB.
- Conversion takes ~170 μs per expression — negligible vs network/LLM latency.

**Why not the alternatives:**
- unicodeit alone: fails on `\frac`, `\mathrm`, accented chars; `\log` -> `łog` bug; leaves `$` delimiters
- flatlatex alone: destroys whitespace in mixed text — unusable
- SymPy pprint: fragile LaTeX parser, heavy dependency, overkill

## Implementation Steps

### Step 1: Add dependencies to `pyproject.toml`

Add to `dependencies`:
```toml
"pylatexenc>=2.10",
"unicodeit>=0.7.5",
"mdit-py-plugins>=0.4.0",
```

`mdit-py-plugins` is already installed (transitive dep of textual), but pin it
explicitly since we depend on `dollarmath_plugin` directly.

Run `uv sync` after.

### Step 2: Create `src/arxiv_coffee/latex.py` — conversion module

A small, focused module with one public function:

```python
from __future__ import annotations

import re

from pylatexenc.latex2text import LatexNodes2Text
import unicodeit


# Module-level converter instance (stateless, reusable, thread-safe)
_L2T = LatexNodes2Text()


def latexToUnicode(latex: str) -> str:
    """Convert a LaTeX math expression to Unicode text.

    Uses pylatexenc for macro expansion (\alpha -> α, \frac{a}{b} -> a/b),
    then unicodeit for superscript/subscript conversion (^2 -> ², _i -> ᵢ).
    """
    # Step 1: pylatexenc converts macros to Unicode
    text = _L2T.latex_to_text(latex)
    # Step 2: unicodeit converts super/subscripts to Unicode chars
    try:
        text = unicodeit.replace(text)
    except Exception:
        pass  # unicodeit can fail on edge cases; pylatexenc output is fine
    return text
```

Key design choices:
- Single `LatexNodes2Text()` instance at module level (it's stateless).
  Uses default `math_mode='text'` which strips `$` delimiters automatically.
- `unicodeit.replace()` wrapped in try/except — it can produce garbage on
  edge cases but pylatexenc output is already good as a fallback.
- The function receives the *content inside* `$...$`, not the delimiters
  themselves (the markdown parser strips those).

### Step 3: Create `src/arxiv_coffee/markdown.py` — custom Markdown widget

This is the core integration. A `MathMarkdown` widget that extends Textual's
`Markdown` with math support:

```python
from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin

from textual.widgets import Markdown
from textual.widgets._markdown import MarkdownBlock, MarkdownParagraph

from arxiv_coffee.latex import latexToUnicode
```

#### 3a. Parser factory

```python
def _createMathParser() -> MarkdownIt:
    """Create a MarkdownIt parser with dollar-math support."""
    return MarkdownIt("gfm-like").use(dollarmath_plugin)
```

This makes `$...$` produce `math_inline` tokens (children of `inline`)
and `$$...$$` produce `math_block` tokens (block-level).

#### 3b. Custom MarkdownBlock subclass for inline math

The key challenge: Textual's `MarkdownBlock._token_to_content()` silently
drops unknown inline token types (like `math_inline`). We must override it.

Approach: Create a `_MathAwareBlock` mixin that overrides `_token_to_content`
to handle `math_inline` tokens. Apply it to `MarkdownParagraph` (and any
other block type that renders inline content: `MarkdownTH`, `MarkdownTD`).

For `math_inline`, the token's `.content` is the raw LaTeX (without `$`).
We convert it via `latexToUnicode()` and render it inline.

**Implementation detail:** Since `_token_to_content` is a complex method
that we'd need to fully re-implement to inject one extra `elif`, the cleaner
approach is to **preprocess tokens** before they reach `_token_to_content`.
We can do this by overriding `build_from_token` on a custom MarkdownBlock
subclass that walks `token.children` and replaces `math_inline` tokens with
`code_inline` tokens whose `.content` is the Unicode-converted math:

```python
class _MathPreprocessMixin:
    """Mixin that converts math_inline tokens to text before rendering."""

    def build_from_token(self, token: Token) -> None:
        """Preprocess math_inline children, then delegate to parent."""
        if token.children:
            new_children = []
            for child in token.children:
                if child.type == "math_inline":
                    # Replace with a plain text token containing Unicode math
                    text_token = Token("text", "", 0)
                    text_token.content = latexToUnicode(child.content)
                    new_children.append(text_token)
                else:
                    new_children.append(child)
            token = token.copy()
            token.children = new_children
        super().build_from_token(token)
```

This is robust because:
- It doesn't duplicate the complex `_token_to_content` logic
- It works for any block type that calls `build_from_token`
- `math_inline` tokens become plain `text` tokens with Unicode content
- The original token is not mutated (`.copy()`)

Apply to paragraph (the main one that shows abstracts):

```python
class _MathParagraph(_MathPreprocessMixin, MarkdownParagraph):
    """Paragraph block with inline math support."""
    pass
```

Also create math-aware versions for table cells if needed (MarkdownTH,
MarkdownTD) — but these are lower priority since tables in arXiv
abstracts are rare.

#### 3c. Custom block widget for `math_block` (display math)

For `$$...$$` blocks, the token appears at block level with type `math_block`.
Handle via `unhandled_token`:

```python
class _MarkdownMathBlock(MarkdownBlock):
    """Renders a display-math block as Unicode text."""

    DEFAULT_CSS = """
    _MarkdownMathBlock {
        margin: 1 0;
        padding: 0 2;
    }
    """

    def __init__(self, markdown: Markdown, token: Token) -> None:
        super().__init__(markdown, token)
        converted = latexToUnicode(token.content.strip())
        from textual.content import Content
        self.set_content(Content(converted))
```

#### 3d. The MathMarkdown widget

```python
class MathMarkdown(Markdown):
    """Markdown widget with LaTeX math rendering support."""

    BLOCKS = {
        **Markdown.BLOCKS,
        "paragraph_open": _MathParagraph,
    }

    def __init__(self, markdown: str | None = None, **kwargs) -> None:
        super().__init__(
            markdown,
            parser_factory=_createMathParser,
            **kwargs,
        )

    def unhandled_token(self, token: Token) -> MarkdownBlock | None:
        """Handle math_block tokens."""
        if token.type == "math_block":
            return _MarkdownMathBlock(self, token)
        return None
```

### Step 4: Replace `Markdown` with `MathMarkdown` in screens

#### 4a. `screens/summary.py`

- Change import: `from arxiv_coffee.markdown import MathMarkdown`
- Replace `Markdown("", id="summary-content")` with `MathMarkdown("", id="summary-content")`
- Replace `self.query_one("#summary-content", Markdown)` with `self.query_one("#summary-content", MathMarkdown)`

#### 4b. `screens/feed.py`

- Add import: `from arxiv_coffee.markdown import MathMarkdown`
- Replace `Markdown("", id="detail-abstract")` with `MathMarkdown("", id="detail-abstract")`
- Replace `self.query_one("#detail-abstract", Markdown)` with `self.query_one("#detail-abstract", MathMarkdown)`
- Remove `Markdown` from the `textual.widgets` import if no longer used elsewhere in the file

### Step 5: Verify Token.copy() availability

The plan uses `token.copy()` in the mixin. Verify that `markdown_it.token.Token`
has a `.copy()` method or use `Token(token.type, token.tag, token.nesting, ...)`
or `copy.copy(token)` as fallback. The Token class is a simple dataclass-like
object, so `copy.copy()` should work.

**Fallback:** Instead of copying the token, create a new Token with the same
attributes but different children list. Or mutate children in-place (they are
not reused by the parser).

### Step 6: Add CSS for math blocks (optional polish)

Add to the screen CSS or to `MathMarkdown`'s DEFAULT_CSS:

```css
_MarkdownMathBlock {
    margin: 1 0;
    padding: 0 4;
    color: $text;
}
```

This gives display-math blocks some visual breathing room.

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Edit | Add `pylatexenc`, `unicodeit`, `mdit-py-plugins` deps |
| `src/arxiv_coffee/latex.py` | Create | `latexToUnicode()` conversion function |
| `src/arxiv_coffee/markdown.py` | Create | `MathMarkdown` widget + helper classes |
| `src/arxiv_coffee/screens/summary.py` | Edit | Swap `Markdown` -> `MathMarkdown` |
| `src/arxiv_coffee/screens/feed.py` | Edit | Swap `Markdown` -> `MathMarkdown` |

## What This Does NOT Do

- No pixel-perfect rendering of matrices, multi-line equations, or complex fractions
  with horizontal bars. This is a fundamental terminal limitation.
- No image-protocol rendering (Kitty/iTerm2 graphics). Would require detecting
  terminal capabilities and is fragile.
- No SymPy 2D ASCII art. Too fragile for arbitrary LaTeX and too heavy a dependency.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `Token.copy()` may not exist | Use `copy.copy(token)` or construct new Token |
| `_token_to_content` private API changes in Textual updates | The mixin approach avoids reimplementing it entirely — only `build_from_token` is overridden, which is more stable |
| pylatexenc slow on very long LaTeX | Unlikely in practice; abstracts are ~200 words. Could add a length cutoff if needed |
| `unicodeit` produces garbage on edge cases | Wrapped in try/except; pylatexenc output is the baseline |
| `MarkdownParagraph` internals change | We only subclass it and add a mixin — minimal coupling |
| Textual's `BLOCKS` dict format changes | We spread `Markdown.BLOCKS` — if keys change, we inherit the change |

## Testing Strategy

Since there is no test suite yet, manual verification:

1. Run the app: `uv run arxiv-coffee`
2. Fetch papers from a math-heavy category (e.g., `hep-ph`, `math.AG`)
3. Open the detail panel (`d` key) and verify abstracts render Greek letters,
   superscripts, subscripts, fractions, and square roots as Unicode
4. Generate a summary and open it — verify the summary screen renders math
5. Check that non-math markdown (headers, bold, links, lists) still renders
   correctly (regression test)

Optional: create a test markdown file with known LaTeX and load it in
SummaryScreen to verify rendering without needing arXiv API access.
