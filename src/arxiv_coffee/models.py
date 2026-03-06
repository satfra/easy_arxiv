from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


@dataclass
class Paper:
    """A single arXiv paper with metadata and optional relevance info."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published: datetime
    pdf_url: str
    primary_category: str = ""
    relevance_score: float | None = None
    relevance_reason: str | None = None

    @property
    def short_id(self) -> str:
        """Return the numeric arXiv ID (e.g. '2603.01234')."""
        return self.arxiv_id.split("/")[-1].replace("abs/", "")

    @property
    def url(self) -> str:
        """Return the abstract page URL."""
        return f"https://arxiv.org/abs/{self.short_id}"

    def toDict(self) -> dict:
        """Serialize to a plain dict suitable for JSON output.

        The ``published`` datetime is converted to an ISO 8601 string so
        the result can be passed directly to ``json.dumps``.
        """
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "categories": self.categories,
            "published": self.published.isoformat(),
            "pdf_url": self.pdf_url,
            "primary_category": self.primary_category,
            "relevance_score": self.relevance_score,
            "relevance_reason": self.relevance_reason,
        }

    @classmethod
    def fromDict(cls, data: dict) -> Paper:
        """Reconstruct a Paper from a dict (e.g. parsed from JSON).

        Handles the ISO 8601 ``published`` string and missing optional
        fields gracefully.
        """
        published_raw = data["published"]
        if isinstance(published_raw, str):
            published = datetime.fromisoformat(published_raw)
        else:
            published = published_raw
        # Ensure timezone-aware
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        return cls(
            arxiv_id=data["arxiv_id"],
            title=data["title"],
            authors=data["authors"],
            abstract=data["abstract"],
            categories=data["categories"],
            published=published,
            pdf_url=data["pdf_url"],
            primary_category=data.get("primary_category", ""),
            relevance_score=data.get("relevance_score"),
            relevance_reason=data.get("relevance_reason"),
        )


def writePapersJsonl(papers: list[Paper], file: IO[str] | None = None) -> None:
    """Write papers as JSON Lines to a file object (default: stdout)."""
    out = file or sys.stdout
    for paper in papers:
        out.write(json.dumps(paper.toDict(), ensure_ascii=False) + "\n")
    out.flush()


def readPapersJsonl(file: IO[str] | None = None) -> list[Paper]:
    """Read papers from JSON Lines on a file object (default: stdin)."""
    src = file or sys.stdin
    papers: list[Paper] = []
    for line in src:
        line = line.strip()
        if not line:
            continue
        papers.append(Paper.fromDict(json.loads(line)))
    return papers


@dataclass
class SummaryResult:
    """Result of an AI summarization of a paper."""

    paper: Paper
    summary_text: str
    generated_at: datetime
    model_used: str
    output_path: Path = field(default_factory=lambda: Path())


@dataclass
class AppConfig:
    """Application configuration loaded from config.toml."""

    # LLM settings
    api_key: str = ""
    model: str = "openai/gpt-4o"
    base_url: str = ""
    requests_per_minute: int = 0

    # arXiv settings
    categories: list[str] = field(default_factory=lambda: ["hep-ph"])
    max_papers: int = 100
    include_cross_posts: bool = False

    # Paths
    interests_file: Path = field(
        default_factory=lambda: (
            Path.home() / ".config" / "arxiv-coffee" / "interests.md"
        )
    )
    output_dir: Path = field(
        default_factory=lambda: Path.home() / "arxiv-coffee-library"
    )

    @property
    def config_dir(self) -> Path:
        return Path.home() / ".config" / "arxiv-coffee"

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.toml"
