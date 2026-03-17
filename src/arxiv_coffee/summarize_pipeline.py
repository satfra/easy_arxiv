from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from arxiv_coffee.library import addToLibrary
from arxiv_coffee.llm import createRateLimiter, summarizePaper
from arxiv_coffee.models import AppConfig, Paper, SummaryResult
from arxiv_coffee.pdf_extractor import downloadAndExtract


@dataclass
class PipelineProgress:
    """Snapshot of the summarization pipeline progress."""

    downloading: int
    summarizing: int
    done: int
    total: int


@dataclass
class PipelineResult:
    """Final result of a summarization pipeline run."""

    success: int
    errors: int
    total: int

    @property
    def summary(self) -> str:
        """Human-readable summary string."""
        text = f"Completed: {self.success} summarized"
        if self.errors:
            text += f", {self.errors} failed"
        return text


async def summarizePapers(
    papers: list[Paper],
    config: AppConfig,
    *,
    on_progress: Callable[[PipelineProgress], None] | None = None,
) -> PipelineResult:
    """Download, extract, and summarize papers concurrently.

    This is the core orchestration function for the summarization
    pipeline.  It manages rate limiting, concurrency, and library writes
    without any UI dependency.

    ``on_progress`` is called whenever the pipeline state changes
    (a paper starts downloading, moves to summarization, or finishes).
    The caller can use this to update a progress bar or status label.
    """
    total = len(papers)
    if total == 0:
        return PipelineResult(success=0, errors=0, total=0)

    limiter = createRateLimiter(config)
    library_lock = asyncio.Lock()
    downloading = 0
    summarizing = 0
    done = 0

    def _emitProgress() -> None:
        if on_progress is not None:
            on_progress(
                PipelineProgress(
                    downloading=downloading,
                    summarizing=summarizing,
                    done=done,
                    total=total,
                )
            )

    async def _processPaper(paper: Paper) -> bool:
        """Download, summarize, and save a single paper."""
        nonlocal downloading, summarizing, done
        phase = "pending"
        try:
            # -- Download phase --
            phase = "downloading"
            downloading += 1
            _emitProgress()
            full_text = await downloadAndExtract(paper)

            # -- Summarize phase --
            phase = "summarizing"
            downloading -= 1
            summarizing += 1
            _emitProgress()
            summary_text = await summarizePaper(
                paper, full_text, config, limiter=limiter
            )

            result = SummaryResult(
                paper=paper,
                summary_text=summary_text,
                generated_at=datetime.now(timezone.utc),
                model_used=config.model,
            )
            async with library_lock:
                addToLibrary(result, config.output_dir)

            # -- Done --
            summarizing -= 1
            done += 1
            _emitProgress()
            return True

        except Exception as exc:
            logger.warning("Failed to process paper '%s': %s", paper.title, exc)
            # Undo whichever phase this paper was in.
            if phase == "downloading":
                downloading -= 1
            elif phase == "summarizing":
                summarizing -= 1
            done += 1
            _emitProgress()
            return False

    results = await asyncio.gather(*(_processPaper(p) for p in papers))

    success = sum(results)
    errors = total - success
    return PipelineResult(success=success, errors=errors, total=total)
