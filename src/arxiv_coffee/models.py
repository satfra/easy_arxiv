from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


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

    # arXiv settings
    categories: list[str] = field(default_factory=lambda: ["hep-ph"])
    max_papers: int = 50

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
