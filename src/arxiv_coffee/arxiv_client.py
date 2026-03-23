from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import arxiv

from arxiv_coffee.models import AppConfig, Paper


@dataclass
class FetchRequest:
    """Validated parameters for a paper fetch operation."""

    categories: list[str]
    max_papers: int
    include_cross_posts: bool
    use_dates: bool = False
    start: datetime | None = None
    end: datetime | None = None


def parseFetchInputs(
    *,
    category: str,
    max_papers_str: str,
    use_dates: bool,
    include_cross_posts: bool,
    start_str: str = "",
    end_str: str = "",
    config: AppConfig,
) -> FetchRequest:
    """Parse and validate raw fetch form inputs into a FetchRequest.

    Raises ``ValueError`` with a user-friendly message when any input is
    invalid (e.g. bad date format, start > end).
    """
    max_papers = int(max_papers_str) if max_papers_str.isdigit() else config.max_papers
    categories = [category] if category else config.categories

    start: datetime | None = None
    end: datetime | None = None

    if use_dates:
        start_stripped = start_str.strip()
        end_stripped = end_str.strip()

        if not start_stripped or not end_stripped:
            raise ValueError("Enter both start and end dates (YYYY-MM-DD).")

        try:
            start = datetime.strptime(start_stripped, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            end = datetime.strptime(end_stripped, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.") from None

        if start > end:
            raise ValueError("Start date must be before end date.")

    return FetchRequest(
        categories=categories,
        max_papers=max_papers,
        include_cross_posts=include_cross_posts,
        use_dates=use_dates,
        start=start,
        end=end,
    )


# arXiv announces new papers at ~20:00 US Eastern on weekdays.
# Submissions close at 14:00 ET, but the batch is not visible on arXiv
# until the 20:00 announcement.  We use the announcement hour for the
# window end so it only advances once papers are actually available,
# but the submission hour for the window start because paper.published
# reflects submission time, not announcement time.
_ARXIV_TZ = ZoneInfo("US/Eastern")
_ANNOUNCEMENT_HOUR = 20  # when the batch becomes visible on arXiv
_SUBMISSION_HOUR = 14    # when submissions close for each batch


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
    per weekday.  Submissions close at 14:00 US/Eastern, but the batch
    is published at ~20:00 ET.  The window end uses 20:00 so it only
    advances once papers are actually visible.  The window start uses
    14:00 (submission close) because paper.published reflects submission
    time, not announcement time.

    On Monday the window covers Friday 14:00 ET -> Monday 20:00 ET
    (weekend submissions are batched together).
    """
    now_et = datetime.now(_ARXIV_TZ)

    # Window end: the most recent announcement (20:00 ET on a weekday).
    today_announcement = now_et.replace(hour=_ANNOUNCEMENT_HOUR, minute=0, second=0, microsecond=0)

    if now_et >= today_announcement:
        # We are past today's announcement, so the latest window ends now.
        end_cutoff = today_announcement
    else:
        # Before today's announcement — the latest completed window ended at
        # yesterday's announcement (or last Friday if today is Mon/Sat/Sun).
        end_cutoff = today_announcement - timedelta(days=1)

    # Walk backwards over weekends: if end_cutoff falls on Sat/Sun, step
    # back to Friday.
    while end_cutoff.weekday() >= 5:  # 5=Saturday, 6=Sunday
        end_cutoff -= timedelta(days=1)

    # The start of the window is the previous weekday at submission close
    # (14:00 ET), because that is where the preceding batch ends and
    # paper.published timestamps are set at submission time.
    start_cutoff = end_cutoff - timedelta(days=1)
    while start_cutoff.weekday() >= 5:
        start_cutoff -= timedelta(days=1)
    start_cutoff = start_cutoff.replace(hour=_SUBMISSION_HOUR, minute=0, second=0, microsecond=0)

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
    announcement window (between two consecutive weekday 20:00 ET
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
