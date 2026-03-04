from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable

import litellm

from arxiv_coffee.models import AppConfig, Paper

logger = logging.getLogger(__name__)

# Suppress litellm's noisy logging
litellm.suppress_debug_info = True
litellm.drop_params = True

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

FILTER_SYSTEM_PROMPT = """\
You are a research assistant helping a scientist find relevant arXiv papers.
You will receive:
1. A description of the user's research interests.
2. A list of papers, each with an ID, title, and abstract.

For each paper, evaluate how relevant it is to the user's interests on a scale
from 0 (completely irrelevant) to 10 (exactly their area of research).

Respond with a JSON array. Each element must have exactly these fields:
- "id": the paper ID (string, exactly as given)
- "score": relevance score (integer, 0-10)
- "reason": a brief one-sentence explanation of why this score was given

Return ONLY the JSON array, no other text. Example:
[{"id": "2603.01234v1", "score": 8, "reason": "Directly addresses SUSY phenomenology at the LHC."}]
"""

SUMMARY_SYSTEM_PROMPT = """\
You are a scientific summarizer. You will receive the full text of an academic
paper. Produce a concise but exhaustive summary in markdown format.

Your summary should include:
1. **Motivation**: Why was this study conducted? What gap does it address?
2. **Methods**: What theoretical framework, tools, or techniques were used?
3. **Key Results**: What are the main findings? Include important numbers,
   limits, or equations where relevant.
4. **Conclusions**: What do the authors conclude? What are the implications?
5. **Outlook**: Any future directions mentioned?

Guidelines:
- Be precise and technical — the reader is a physicist.
- Use LaTeX notation for equations where helpful (e.g. $m_H = 125$ GeV).
- For important standalone equations, use display math with double dollar signs
  on their own line (e.g. $$E = mc^2$$) so they render prominently.
- Keep the summary between 300-600 words.
- Do NOT include the abstract (it will be added separately).
- Use markdown headers (##) for each section.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _modelHandlesAuth(model: str) -> bool:
    """Check if a model provider handles authentication internally.

    Some providers (e.g. github_copilot/) use OAuth device flow managed
    by litellm and do not require a user-supplied API key.
    """
    return model.startswith("github_copilot/")


def _buildCompletionKwargs(config: AppConfig) -> dict:
    """Build common kwargs for litellm calls from config."""
    kwargs: dict = {
        "model": config.model,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return kwargs


def _formatPapersForFilter(papers: list[Paper]) -> str:
    """Format papers into a text block for the filter prompt."""
    lines: list[str] = []
    for p in papers:
        lines.append(f"ID: {p.short_id}")
        lines.append(f"Title: {p.title}")
        lines.append(f"Abstract: {p.abstract}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Async token-bucket rate limiter for API requests.

    When ``rpm`` is 0 or negative the limiter is disabled and acts as a
    simple concurrency gate (``max_concurrent`` only).
    """

    def __init__(self, *, rpm: int = 0, max_concurrent: int = 4) -> None:
        self._rpm = max(rpm, 0)
        self._interval = 60.0 / self._rpm if self._rpm > 0 else 0.0
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._timestamps: list[float] = []

    async def acquire(self) -> None:
        """Wait until a request is allowed, then reserve a slot."""
        await self._semaphore.acquire()
        if self._rpm <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            window_start = now - 60.0
            # Evict timestamps older than the 60-second window
            self._timestamps = [t for t in self._timestamps if t > window_start]

            if len(self._timestamps) >= self._rpm:
                # Must wait until the oldest request exits the window
                sleep_for = self._timestamps[0] - window_start
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

            self._timestamps.append(time.monotonic())

    def release(self) -> None:
        """Release the concurrency slot."""
        self._semaphore.release()


def createRateLimiter(config: AppConfig, *, max_concurrent: int = 4) -> _RateLimiter:
    """Create a rate limiter from the application config.

    Use this when you need to share a single limiter across multiple calls
    (e.g. the summarisation loop in the feed screen).
    """
    return _RateLimiter(rpm=config.requests_per_minute, max_concurrent=max_concurrent)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _filterBatch(
    batch: list[Paper],
    batch_index: int,
    interests: str,
    kwargs: dict,
    limiter: _RateLimiter,
) -> dict[str, tuple[float, str]]:
    """Score a single batch of papers via the LLM.

    Uses a rate limiter to honour the configured requests-per-minute cap.
    Returns a dict mapping paper short_id to (score, reason).
    """
    await limiter.acquire()
    try:
        papers_text = _formatPapersForFilter(batch)
        user_message = (
            f"## My Research Interests\n\n{interests}\n\n"
            f"## Papers to Evaluate\n\n{papers_text}"
        )

        response = await litellm.acompletion(
            messages=[
                {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            **kwargs,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")]
            raw = raw.strip()

        scored: dict[str, tuple[float, str]] = {}
        try:
            results = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM filter response, skipping batch %d",
                batch_index,
            )
            return scored

        for entry in results:
            paper_id = str(entry.get("id", ""))
            score = float(entry.get("score", 0))
            reason = str(entry.get("reason", ""))
            scored[paper_id] = (score, reason)

        return scored
    finally:
        limiter.release()


async def filterPapersByRelevance(
    papers: list[Paper],
    interests: str,
    config: AppConfig,
    *,
    batch_size: int = 5,
    max_concurrent: int = 4,
    on_batch_done: Callable[[int, int], None] | None = None,
) -> list[Paper]:
    """Use an LLM to score papers by relevance to the user's interests.

    Papers are sent in small batches and evaluated concurrently to reduce
    wall-clock time. Each paper's relevance_score and relevance_reason are
    populated. Returns all papers sorted by descending relevance score.

    ``on_batch_done`` is called with (completed_count, total_batches) after
    each batch finishes, useful for progress reporting in the UI.
    """
    if not papers:
        return []

    if not config.api_key and not _modelHandlesAuth(config.model):
        raise ValueError("No API key configured. Set llm.api_key in config.toml.")

    kwargs = _buildCompletionKwargs(config)
    limiter = _RateLimiter(
        rpm=config.requests_per_minute, max_concurrent=max_concurrent
    )

    batches = [papers[i : i + batch_size] for i in range(0, len(papers), batch_size)]
    total_batches = len(batches)
    completed = 0

    async def _runBatch(batch: list[Paper], index: int) -> dict[str, tuple[float, str]]:
        nonlocal completed
        result = await _filterBatch(batch, index, interests, kwargs, limiter)
        completed += 1
        if on_batch_done is not None:
            on_batch_done(completed, total_batches)
        return result

    # Fire all batches concurrently (limiter gates parallelism + RPM)
    batch_results = await asyncio.gather(
        *(_runBatch(batch, idx) for idx, batch in enumerate(batches))
    )

    # Merge results
    scored: dict[str, tuple[float, str]] = {}
    for partial in batch_results:
        scored.update(partial)

    # Apply scores to papers
    for paper in papers:
        if paper.short_id in scored:
            paper.relevance_score, paper.relevance_reason = scored[paper.short_id]
        else:
            paper.relevance_score = 0.0
            paper.relevance_reason = "Not evaluated"

    # Sort by score descending
    papers.sort(key=lambda p: p.relevance_score or 0.0, reverse=True)
    return papers


async def summarizePaper(
    paper: Paper,
    full_text: str,
    config: AppConfig,
    *,
    max_text_chars: int = 80_000,
    limiter: _RateLimiter | None = None,
) -> str:
    """Use an LLM to generate a summary of a paper from its full text.

    Returns the summary as a markdown string.  When a *limiter* is supplied
    the call will respect the configured requests-per-minute cap.
    """
    if not config.api_key and not _modelHandlesAuth(config.model):
        raise ValueError("No API key configured. Set llm.api_key in config.toml.")

    kwargs = _buildCompletionKwargs(config)

    # Truncate very long papers to stay within context limits
    text = full_text[:max_text_chars]
    if len(full_text) > max_text_chars:
        text += "\n\n[... text truncated for length ...]"

    user_message = (
        f"# {paper.title}\n\n**Authors:** {', '.join(paper.authors)}\n\n---\n\n{text}"
    )

    if limiter is not None:
        await limiter.acquire()
    try:
        response = await litellm.acompletion(
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            **kwargs,
        )
        return response.choices[0].message.content.strip()
    finally:
        if limiter is not None:
            limiter.release()
