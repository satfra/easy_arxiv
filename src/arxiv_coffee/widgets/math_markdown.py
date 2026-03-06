from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Markdown
from textual.widgets._markdown import MarkdownBlock, MarkdownParagraph

from arxiv_coffee.latex import latexToUnicode
from arxiv_coffee.terminal_caps import HAS_MATH_IMAGE


def _createMathParser() -> MarkdownIt:
    """Create a MarkdownIt parser with dollar-math support."""
    return MarkdownIt("gfm-like").use(dollarmath_plugin)


class _MathPreprocessMixin:
    """Mixin that converts math_inline tokens to text before rendering."""

    def build_from_token(self, token: Token) -> None:
        """Preprocess math_inline children, then delegate to parent."""
        if token.children:
            new_children = []
            for child in token.children:
                if child.type == "math_inline":
                    text_token = Token("text", "", 0)
                    text_token.content = latexToUnicode(child.content)
                    new_children.append(text_token)
                else:
                    new_children.append(child)
            token = token.copy(children=new_children)
        super().build_from_token(token)


class _MathParagraph(_MathPreprocessMixin, MarkdownParagraph):
    """Paragraph block with inline math support."""


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
