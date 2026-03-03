from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import arxiv

from arxiv_coffee.models import AppConfig, Paper

# arXiv daily submission cutoff: 14:00 US Eastern on weekdays.
_ARXIV_TZ = ZoneInfo("US/Eastern")
_CUTOFF_HOUR = 14


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


def _isCrossPost(paper: Paper, categories: list[str]) -> bool:
    """Check whether a paper is a cross-post for the given categories.

    A paper is a cross-post when its primary_category does not match any
    of the categories being searched.
    """
    return paper.primary_category not in categories


def _latestAnnouncementWindow() -> tuple[datetime, datetime]:
    """Return the (start, end) UTC datetimes of the most recent arXiv
    announcement window.

    arXiv accepts submissions continuously but announces new papers once
    per weekday.  The daily cutoff is 14:00 US/Eastern; papers submitted
    between two consecutive cutoffs form one announcement batch.

    On Monday the window covers Friday 14:00 ET -> Monday 14:00 ET
    (weekend submissions are batched together).
    """
    now_et = datetime.now(_ARXIV_TZ)

    # Current cutoff today at 14:00 ET.
    today_cutoff = now_et.replace(hour=_CUTOFF_HOUR, minute=0, second=0, microsecond=0)

    if now_et >= today_cutoff:
        # We are past today's cutoff, so the latest window ends now.
        end_cutoff = today_cutoff
    else:
        # Before today's cutoff — the latest completed window ended at
        # yesterday's cutoff (or last Friday if today is Monday).
        end_cutoff = today_cutoff - timedelta(days=1)

    # Walk backwards over weekends: if end_cutoff falls on Sat/Sun, step
    # back to Friday.
    while end_cutoff.weekday() >= 5:  # 5=Saturday, 6=Sunday
        end_cutoff -= timedelta(days=1)

    # The start of the window is the previous weekday cutoff.
    start_cutoff = end_cutoff - timedelta(days=1)
    while start_cutoff.weekday() >= 5:
        start_cutoff -= timedelta(days=1)

    # Convert to UTC.
    start_utc = start_cutoff.astimezone(timezone.utc)
    end_utc = end_cutoff.astimezone(timezone.utc)
    return start_utc, end_utc


async def fetchLatestPapers(
    config: AppConfig,
    categories: list[str] | None = None,
    max_results: int | None = None,
    *,
    include_cross_posts: bool | None = None,
) -> list[Paper]:
    """Fetch papers from the most recent arXiv announcement window.

    Only papers whose submission timestamp falls within the latest
    announcement window (between two consecutive weekday 14:00 ET
    cutoffs) are returned.  This matches the papers shown on the arXiv
    ``/list/<category>/new`` page.

    Runs the blocking arxiv client in a thread to keep the event loop
    free.  When *include_cross_posts* is False, papers whose
    primary_category does not match any of the searched categories are
    excluded.
    """
    cats = categories or config.categories
    limit = max_results or config.max_papers
    cross = (
        include_cross_posts
        if include_cross_posts is not None
        else config.include_cross_posts
    )
    query = _buildCategoryQuery(cats)

    window_start, window_end = _latestAnnouncementWindow()

    # We need to fetch enough results to cover the full announcement
    # window.  A typical day has 30-80 papers per large category
    # (including cross-posts), so 500 is a safe upper bound.
    fetch_limit = max(limit * 5, 500)

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
            # Stop once we've gone past the window start.
            if paper.published < window_start:
                break
            # Skip papers submitted after the window end (not yet
            # announced).
            if paper.published > window_end:
                continue
            if not cross and _isCrossPost(paper, cats):
                continue
            papers.append(paper)
            if len(papers) >= limit:
                break
        return papers

    return await asyncio.to_thread(_fetch)


async def fetchPapersByDateRange(
    config: AppConfig,
    start: datetime,
    end: datetime,
    categories: list[str] | None = None,
    max_results: int | None = None,
    *,
    include_cross_posts: bool | None = None,
) -> list[Paper]:
    """Fetch papers from the given categories within a date range.

    The arxiv API doesn't natively support date filtering in the query,
    so we fetch sorted by date and filter client-side.  When
    *include_cross_posts* is False, cross-listed papers are excluded.
    """
    cats = categories or config.categories
    limit = max_results or config.max_papers
    cross = (
        include_cross_posts
        if include_cross_posts is not None
        else config.include_cross_posts
    )
    query = _buildCategoryQuery(cats)

    # Fetch more than needed since we filter by date (and possibly cross-posts)
    fetch_limit = limit * 3 if cross else limit * 5

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
                if not cross and _isCrossPost(paper, cats):
                    continue
                papers.append(paper)
            if len(papers) >= limit:
                break
        return papers

    return await asyncio.to_thread(_fetch)
