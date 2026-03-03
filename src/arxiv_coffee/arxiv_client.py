from __future__ import annotations

import asyncio
from datetime import datetime

import arxiv

from arxiv_coffee.models import AppConfig, Paper


def _resultToPaper(result: arxiv.Result) -> Paper:
    """Convert an arxiv.Result to our Paper dataclass."""
    return Paper(
        arxiv_id=result.entry_id,
        title=result.title.replace("\n", " ").strip(),
        authors=[a.name for a in result.authors],
        abstract=result.summary.strip(),
        categories=list(result.categories),
        primary_category=result.primary_category,
        published=result.published,
        pdf_url=result.pdf_url or "",
    )


def _buildCategoryQuery(categories: list[str]) -> str:
    """Build an arxiv API query string for one or more categories.

    Example: ["hep-ph", "hep-th"] -> "cat:hep-ph OR cat:hep-th"
    """
    parts = [f"cat:{cat}" for cat in categories]
    return " OR ".join(parts)


async def fetchLatestPapers(
    config: AppConfig,
    categories: list[str] | None = None,
    max_results: int | None = None,
) -> list[Paper]:
    """Fetch the most recent papers from the given arXiv categories.

    Runs the blocking arxiv client in a thread to keep the event loop free.
    """
    cats = categories or config.categories
    limit = max_results or config.max_papers
    query = _buildCategoryQuery(cats)

    search = arxiv.Search(
        query=query,
        max_results=limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    def _fetch() -> list[Paper]:
        client = arxiv.Client(page_size=min(limit, 100), delay_seconds=3.0)
        return [_resultToPaper(r) for r in client.results(search)]

    return await asyncio.to_thread(_fetch)


async def fetchPapersByDateRange(
    config: AppConfig,
    start: datetime,
    end: datetime,
    categories: list[str] | None = None,
    max_results: int | None = None,
) -> list[Paper]:
    """Fetch papers from the given categories within a date range.

    The arxiv API doesn't natively support date filtering in the query,
    so we fetch sorted by date and filter client-side.
    """
    cats = categories or config.categories
    limit = max_results or config.max_papers
    query = _buildCategoryQuery(cats)

    # Fetch more than needed since we'll filter by date
    fetch_limit = limit * 3

    search = arxiv.Search(
        query=query,
        max_results=fetch_limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    def _fetch() -> list[Paper]:
        client = arxiv.Client(page_size=min(fetch_limit, 100), delay_seconds=3.0)
        papers: list[Paper] = []
        for result in client.results(search):
            paper = _resultToPaper(result)
            # Stop early if we've gone past the start date
            if paper.published < start:
                break
            if paper.published <= end:
                papers.append(paper)
            if len(papers) >= limit:
                break
        return papers

    return await asyncio.to_thread(_fetch)
