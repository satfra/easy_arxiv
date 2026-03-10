from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin


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
# Markdown → HTML conversion
# ---------------------------------------------------------------------------


def _buildParser() -> MarkdownIt:
    """Create a MarkdownIt parser with GFM-like rules and dollar-math support."""
    return MarkdownIt("gfm-like").use(dollarmath_plugin)


def convertMarkdownToHtml(md_content: str) -> str:
    """Convert a markdown string (with LaTeX math) to an HTML fragment.

    Inline math ($...$) is emitted as ``\\(...\\)`` delimiters and display
    math ($$...$$) as ``\\[...\\]`` delimiters for MathJax to render
    client-side in the browser.

    The returned string is an HTML fragment suitable for insertion into a
    <body> element; it does not include <html> / <head> / <body> tags.
    """
    md = _buildParser()

    # Override the renderer for math tokens to emit MathJax delimiters.
    def _renderMathInline(
        slf: object, tokens: list, idx: int, options: object, env: object
    ) -> str:
        return f"\\({tokens[idx].content}\\)"

    def _renderMathBlock(
        slf: object, tokens: list, idx: int, options: object, env: object
    ) -> str:
        return f"\\[{tokens[idx].content}\\]"

    md.add_render_rule("math_inline", _renderMathInline)
    md.add_render_rule("math_block", _renderMathBlock)

    return md.render(md_content)


# ---------------------------------------------------------------------------
# HTML document assembly
# ---------------------------------------------------------------------------


_MATHJAX_CONFIG = r"""
MathJax = {
  tex: {
    inlineMath: [['\\(', '\\)']],
    displayMath: [['\\[', '\\]']]
  }
};
""".strip()

_MATHJAX_SRC = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"


def wrapInHtmlDocument(body: str, title: str) -> str:
    """Wrap an HTML fragment in a complete HTML5 document.

    All styles are inline. LaTeX math is rendered client-side by MathJax
    loaded from a CDN, so an internet connection and JavaScript are required.
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
        f"<script>\n{_MATHJAX_CONFIG}\n</script>\n"
        f'<script id="MathJax-script" async '
        f'src="{_MATHJAX_SRC}"></script>\n'
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
    a separate section. Math is rendered client-side by MathJax.
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
