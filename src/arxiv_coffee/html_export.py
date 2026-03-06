from __future__ import annotations

import base64
import io
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

matplotlib.use("agg")


# ---------------------------------------------------------------------------
# CSS for the HTML documents
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
                 sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
    font-size: 16px;
    line-height: 1.6;
    color: #24292e;
    max-width: 860px;
    margin: 0 auto;
    padding: 32px 24px;
    background: #ffffff;
}
h1 {
    font-size: 1.75em;
    font-weight: 600;
    border-bottom: 1px solid #eaecef;
    padding-bottom: 0.3em;
    margin-top: 0;
    margin-bottom: 0.6em;
}
h2 {
    font-size: 1.3em;
    font-weight: 600;
    border-bottom: 1px solid #eaecef;
    padding-bottom: 0.25em;
    margin-top: 1.8em;
    margin-bottom: 0.6em;
}
h3 {
    font-size: 1.1em;
    font-weight: 600;
    margin-top: 1.4em;
    margin-bottom: 0.4em;
}
p { margin: 0.6em 0; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; }
hr {
    border: none;
    border-top: 1px solid #eaecef;
    margin: 1.8em 0;
}
code {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.875em;
    background: #f6f8fa;
    padding: 0.2em 0.4em;
    border-radius: 3px;
}
pre {
    background: #f6f8fa;
    padding: 16px;
    border-radius: 6px;
    overflow-x: auto;
    line-height: 1.45;
}
pre code {
    background: none;
    padding: 0;
    font-size: 0.875em;
}
blockquote {
    border-left: 4px solid #dfe2e5;
    padding: 0 1em;
    color: #6a737d;
    margin: 0.8em 0;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}
th, td {
    border: 1px solid #dfe2e5;
    padding: 6px 13px;
    text-align: left;
}
th { background: #f6f8fa; font-weight: 600; }
tr:nth-child(even) td { background: #f9fafb; }
img.math-inline {
    vertical-align: middle;
    height: 1.25em;
    margin: 0 0.1em;
}
img.math-display {
    display: block;
    margin: 1.2em auto;
    max-width: 100%;
}
ul, ol { padding-left: 2em; margin: 0.6em 0; }
li { margin: 0.2em 0; }
.toc {
    background: #f6f8fa;
    border: 1px solid #eaecef;
    border-radius: 6px;
    padding: 16px 20px;
    margin-bottom: 2em;
}
.toc h2 {
    border: none;
    margin-top: 0;
    font-size: 1em;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6a737d;
}
.toc ol { margin: 0; }
.toc li { margin: 0.3em 0; }
.paper-section { margin-bottom: 3em; }
""".strip()


# ---------------------------------------------------------------------------
# Math rendering
# ---------------------------------------------------------------------------


def _renderMathToPng(latex: str, *, display: bool = False) -> bytes:
    """Render a LaTeX expression to PNG bytes using matplotlib mathtext.

    Raises ValueError if the expression cannot be rendered.
    """
    dpi = 180 if display else 150
    # matplotlib mathtext requires the expression to be wrapped in $...$
    expr = f"${latex}$"

    fig = plt.figure(figsize=(0.01, 0.01))
    try:
        text = fig.text(0, 0, expr, fontsize=13 if display else 11)
        fig.canvas.draw()
        bbox = text.get_window_extent(renderer=fig.canvas.get_renderer())
        # Add small padding
        pad = 4
        width = max(1, int(bbox.width) + pad * 2)
        height = max(1, int(bbox.height) + pad * 2)
        fig.set_size_inches(width / dpi, height / dpi)
        text.set_position((pad / width, pad / height))
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            bbox_inches=None,
            facecolor="white",
            edgecolor="none",
        )
        buf.seek(0)
        return buf.read()
    except Exception as exc:
        raise ValueError(f"Failed to render LaTeX expression: {latex!r}") from exc
    finally:
        plt.close(fig)


def _mathToImgTag(latex: str, *, display: bool = False) -> str:
    """Render LaTeX to a base64-encoded PNG img tag."""
    png_bytes = _renderMathToPng(latex, display=display)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    css_class = "math-display" if display else "math-inline"
    alt = latex.replace('"', "&quot;")
    return f'<img class="{css_class}" src="data:image/png;base64,{b64}" alt="{alt}">'


# ---------------------------------------------------------------------------
# Markdown → HTML conversion
# ---------------------------------------------------------------------------


def _buildParser() -> MarkdownIt:
    """Create a MarkdownIt parser with GFM-like rules and dollar-math support."""
    return MarkdownIt("gfm-like").use(dollarmath_plugin)


def convertMarkdownToHtml(md_content: str) -> str:
    """Convert a markdown string (with LaTeX math) to an HTML fragment.

    Inline math ($...$) is rendered as a small inline PNG image.
    Display math ($$...$$) is rendered as a centred block PNG image.
    All math rendering uses matplotlib mathtext — no JavaScript required.
    The returned string is an HTML fragment suitable for insertion into a
    <body> element; it does not include <html> / <head> / <body> tags.
    """
    md = _buildParser()

    # Override the renderer for math tokens.
    # add_render_rule binds self.renderer as the first arg via __get__, so the
    # effective signature is (self, tokens, idx, options, env).
    def _renderMathInline(
        slf: object, tokens: list, idx: int, options: object, env: object
    ) -> str:
        return _mathToImgTag(tokens[idx].content, display=False)

    def _renderMathBlock(
        slf: object, tokens: list, idx: int, options: object, env: object
    ) -> str:
        return _mathToImgTag(tokens[idx].content, display=True)

    md.add_render_rule("math_inline", _renderMathInline)
    md.add_render_rule("math_block", _renderMathBlock)

    return md.render(md_content)


# ---------------------------------------------------------------------------
# HTML document assembly
# ---------------------------------------------------------------------------


def wrapInHtmlDocument(body: str, title: str) -> str:
    """Wrap an HTML fragment in a complete, self-contained HTML5 document.

    All styles are inline — no external resources, no JavaScript.
    Safe to attach to emails or open in any browser.
    """
    escaped_title = title.replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escaped_title}</title>\n"
        f"<style>\n{_CSS}\n</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# File-level export
# ---------------------------------------------------------------------------


def exportSummaryToHtml(md_path: Path) -> Path:
    """Convert a summary markdown file to a self-contained HTML file.

    Writes the HTML file alongside the markdown file (same directory,
    same base name, .html extension). Returns the path to the HTML file.
    """
    md_content = md_path.read_text(encoding="utf-8")

    # Extract title from first # heading for the <title> tag
    title = md_path.stem
    for line in md_content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    body = convertMarkdownToHtml(md_content)
    html = wrapInHtmlDocument(body, title)

    html_path = md_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    return html_path


# ---------------------------------------------------------------------------
# Digest (multi-summary) export
# ---------------------------------------------------------------------------


def buildDigestHtml(md_paths: list[Path], title: str) -> str:
    """Combine multiple summary markdown files into a single HTML document.

    Produces a page with a table of contents followed by each summary as
    a separate section. All math is pre-rendered as inline PNG images.
    """
    toc_items: list[str] = []
    sections: list[str] = []

    for i, md_path in enumerate(md_paths):
        md_content = md_path.read_text(encoding="utf-8")

        # Extract paper title for TOC
        paper_title = md_path.stem
        for line in md_content.splitlines():
            if line.startswith("# "):
                paper_title = line[2:].strip()
                break

        anchor = f"paper-{i + 1}"
        toc_items.append(f'<li><a href="#{anchor}">{paper_title}</a></li>')

        body_fragment = convertMarkdownToHtml(md_content)
        sections.append(
            f'<div class="paper-section" id="{anchor}">\n{body_fragment}</div>\n'
        )

    toc_html = (
        '<div class="toc">\n'
        "<h2>Contents</h2>\n"
        "<ol>\n" + "\n".join(toc_items) + "\n</ol>\n"
        "</div>\n"
    )

    body = toc_html + "\n".join(sections)
    return wrapInHtmlDocument(body, title)
