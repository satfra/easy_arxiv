from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import fitz
import httpx

from arxiv_coffee.models import Paper


async def downloadPdf(paper: Paper, dest_dir: Path | None = None) -> Path:
    """Download a paper's PDF to a directory. Returns the path to the file.

    If dest_dir is None, a temporary directory is used (caller should clean up).
    """
    if not paper.pdf_url:
        raise ValueError(f"No PDF URL for paper {paper.arxiv_id}")

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="arxiv_coffee_"))
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{paper.short_id.replace('/', '_')}.pdf"
    dest_path = dest_dir / filename

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        response = await client.get(paper.pdf_url)
        response.raise_for_status()
        dest_path.write_bytes(response.content)

    return dest_path


def extractText(pdf_path: Path) -> str:
    """Extract all text from a PDF file using pymupdf.

    Returns the concatenated text from all pages, separated by page breaks.
    """
    doc = fitz.open(str(pdf_path))
    pages: list[str] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        if text.strip():
            pages.append(text)

    doc.close()
    return "\n\n---\n\n".join(pages)


async def downloadAndExtract(paper: Paper, tmp_dir: Path | None = None) -> str:
    """Download a paper's PDF and extract its text. Convenience wrapper.

    Downloads the PDF, extracts text, and cleans up the PDF file.
    """
    pdf_path = await downloadPdf(paper, tmp_dir)
    try:
        text = await asyncio.to_thread(extractText, pdf_path)
    finally:
        # Clean up the downloaded PDF
        if tmp_dir is None:
            pdf_path.unlink(missing_ok=True)
            pdf_path.parent.rmdir()
    return text
