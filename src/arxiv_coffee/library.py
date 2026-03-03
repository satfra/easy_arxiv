from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from arxiv_coffee.models import Paper, SummaryResult


def _slugify(text: str, max_len: int = 60) -> str:
    """Convert a title to a filesystem-safe slug.

    Example: "SUSY at the LHC: A Review" -> "susy-at-the-lhc-a-review"
    """
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len].rstrip("-")


def _buildSummaryPath(result: SummaryResult, output_dir: Path) -> Path:
    """Determine the output path for a paper summary file.

    Format: {output_dir}/{primary_category}/{YYYY-MM-DD}_{slug}.md
    """
    category = result.paper.primary_category or result.paper.categories[0]
    date_str = result.paper.published.strftime("%Y-%m-%d")
    slug = _slugify(result.paper.title)
    filename = f"{date_str}_{slug}.md"
    return output_dir / category / filename


def writeSummaryFile(result: SummaryResult, output_dir: Path) -> Path:
    """Write a paper summary to a structured markdown file.

    Creates the category subdirectory if needed. Returns the path to the
    written file and updates result.output_path.
    """
    path = _buildSummaryPath(result, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    authors_str = ", ".join(result.paper.authors)
    categories_str = ", ".join(result.paper.categories)
    date_str = result.paper.published.strftime("%Y-%m-%d")
    generated_str = result.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    content = (
        f"# {result.paper.title}\n\n"
        f"**Authors:** {authors_str}  \n"
        f"**arXiv:** [{result.paper.short_id}]({result.paper.url})  \n"
        f"**Published:** {date_str}  \n"
        f"**Categories:** {categories_str}\n\n"
        f"---\n\n"
        f"## Abstract\n\n"
        f"{result.paper.abstract}\n\n"
        f"---\n\n"
        f"## Summary\n\n"
        f"{result.summary_text}\n\n"
        f"---\n\n"
        f"*Summarized by {result.model_used} on {generated_str}*\n"
    )

    path.write_text(content, encoding="utf-8")
    result.output_path = path
    return path


def parseSummaryFile(path: Path) -> dict | None:
    """Extract metadata from a summary markdown file.

    Returns a dict with keys: title, short_id, url, date, category, rel_path, path.
    Returns None if the file can't be parsed (missing title).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Title: first line starting with "# "
    title = ""
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    if not title:
        return None

    # arXiv ID and URL from the **arXiv:** line
    short_id = ""
    url = ""
    match = re.search(r"\*\*arXiv:\*\*\s*\[([^\]]+)\]\(([^)]+)\)", text)
    if match:
        short_id = match.group(1)
        url = match.group(2)

    # Published date
    date_str = ""
    match = re.search(r"\*\*Published:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    if match:
        date_str = match.group(1)

    # Category from parent directory name
    category = path.parent.name

    return {
        "title": title,
        "short_id": short_id,
        "url": url,
        "date": date_str,
        "category": category,
        "rel_path": path.name,
        "path": path,
    }


def updateLibraryIndex(output_dir: Path) -> Path:
    """Rebuild the library.md index by scanning all summary files.

    Returns the path to library.md.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "library.md"

    # Collect all summary files grouped by category
    categories: dict[str, list[dict]] = {}

    for md_file in sorted(output_dir.rglob("*.md")):
        # Skip library.md itself
        if md_file.name == "library.md":
            continue
        # Only process files in category subdirectories
        if md_file.parent == output_dir:
            continue

        entry = parseSummaryFile(md_file)
        if entry is None or not entry["short_id"]:
            continue

        cat = entry["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(entry)

    # Sort categories alphabetically, entries by date descending
    lines: list[str] = ["# arxiv-coffee Library\n"]

    for cat in sorted(categories.keys()):
        entries = sorted(categories[cat], key=lambda e: e["date"], reverse=True)
        lines.append(f"\n## {cat}\n")
        lines.append("| Date | Title | arXiv | Summary |")
        lines.append("|------|-------|-------|---------|")
        for e in entries:
            summary_link = f"[summary]({cat}/{e['rel_path']})"
            arxiv_link = f"[{e['short_id']}]({e['url']})"
            lines.append(
                f"| {e['date']} | {e['title']} | {arxiv_link} | {summary_link} |"
            )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"\n---\n\n*Last updated: {timestamp}*\n")

    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def addToLibrary(result: SummaryResult, output_dir: Path) -> Path:
    """Write a summary file and append it to the library index.

    If library.md doesn't exist yet, creates it with a full rebuild.
    Returns the path to the written summary file.
    """
    summary_path = writeSummaryFile(result, output_dir)

    index_path = output_dir / "library.md"
    if not index_path.exists():
        # First entry — do a full rebuild (which will pick up the file we just wrote)
        updateLibraryIndex(output_dir)
        return summary_path

    # Append to existing index
    entry = parseSummaryFile(summary_path)
    if entry is None:
        return summary_path

    content = index_path.read_text(encoding="utf-8")

    cat = entry["category"]
    summary_link = f"[summary]({cat}/{entry['rel_path']})"
    arxiv_link = f"[{entry['short_id']}]({entry['url']})"
    new_row = f"| {entry['date']} | {entry['title']} | {arxiv_link} | {summary_link} |"

    # Find the category section and insert the new row
    section_header = f"## {cat}"
    if section_header in content:
        # Insert after the header row (|------|...)
        lines = content.splitlines()
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                # Skip the header, then the table header, then the separator
                # Find the separator line (|------|...)
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j].startswith("|---"):
                        insert_idx = j + 1
                        break
                break

        if insert_idx is not None:
            lines.insert(insert_idx, new_row)
            # Update timestamp
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("*Last updated:"):
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
                    lines[i] = f"*Last updated: {timestamp}*"
                    break
            index_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            # Fallback: full rebuild
            updateLibraryIndex(output_dir)
    else:
        # New category — full rebuild is simplest
        updateLibraryIndex(output_dir)

    return summary_path
